# weiler_atherton.py
from typing import List, Tuple, Optional, Dict
from geometry import PolygonModel, Ring, Point
from geometry import EPS, point_eq, seg_intersection, point_in_polygon_with_holes, on_segment, orient, is_ccw, signed_area
import math


class Node:
    def __init__(self, pt: Point, is_inter: bool = False, alpha: Optional[float] = None, edge: Optional[tuple] = None):
        self.pt = pt
        self.is_inter = is_inter
        self.alpha = alpha
        # edge三元组: (ring_idx, start_idx, end_idx)
        self.edge = edge
        self.neighbor: Optional['Node'] = None
        self.visited: bool = False
        self.is_entry: Optional[bool] = None

    def __repr__(self):
        return f"Node(pt={self.pt}, inter={self.is_inter}, alpha={self.alpha}, entry={self.is_entry})"


def build_vertex_lists(poly: PolygonModel) -> List[List[Node]]:
    """
    把每个 ring 的顶点转成 Node 列表（仅原始顶点），edge 标记为 (ring_idx, start_idx, end_idx)
    """
    rings_nodes: List[List[Node]] = []
    for r_idx, ring in enumerate(poly.rings):
        n = len(ring)
        if n == 0:
            rings_nodes.append([])
            continue
        nodes = []
        for i, pt in enumerate(ring):
            edge = (r_idx, i, (i + 1) % n)
            nodes.append(Node(pt=pt, is_inter=False, alpha=None, edge=edge))
        rings_nodes.append(nodes)
    return rings_nodes


def insert_intersections(subject: PolygonModel, clipper: PolygonModel):
    """
    找到所有相交点并把交点插入到 subj_nodes 与 clip_nodes 中（按 alpha 排序）。
    返回 subj_nodes, clip_nodes（二者为 List[List[Node]])
    """
    subj_nodes = build_vertex_lists(subject)
    clip_nodes = build_vertex_lists(clipper)

    inter_records: List[Dict] = []

    # 找所有交点记录（记录三元边以及在边上的 alpha）
    for si, sring in enumerate(subject.rings):
        sn = len(sring)
        if sn < 2:
            continue
        for s_idx in range(sn):
            a = sring[s_idx]
            b = sring[(s_idx + 1) % sn]
            for ci, cring in enumerate(clipper.rings):
                cn = len(cring)
                if cn < 2:
                    continue
                for c_idx in range(cn):
                    c = cring[c_idx]
                    d = cring[(c_idx + 1) % cn]
                    ip = seg_intersection(a, b, c, d)
                    if ip is None:
                        continue

                    # 计算 alpha：沿边从 start 点到 end 点的参数 [0,1]
                    def calc_alpha(p, u, v):
                        ux, uy = u
                        vx, vy = v
                        dx = vx - ux
                        dy = vy - uy
                        denom = dx * dx + dy * dy
                        if denom < EPS:
                            return 0.0
                        t = ((p[0] - ux) * dx + (p[1] - uy) * dy) / denom
                        return max(0.0, min(1.0, t))

                    a_alpha = calc_alpha(ip, a, b)
                    c_alpha = calc_alpha(ip, c, d)
                    inter_records.append({
                        'pt': ip,
                        'subj_edge': (si, s_idx, (s_idx + 1) % sn),
                        'subj_alpha': a_alpha,
                        'clip_edge': (ci, c_idx, (c_idx + 1) % cn),
                        'clip_alpha': c_alpha
                    })

    # 去重 inter_records（基于坐标近似），并把相同交点的记录合并（保留最小 alpha）
    unique_recs: List[Dict] = []
    for rec in inter_records:
        merged = False
        for u in unique_recs:
            if point_eq(u['pt'], rec['pt']):
                # 合并：保留两边 alpha 的最小值（稳定插入顺序）
                u['subj_alpha'] = min(u['subj_alpha'], rec['subj_alpha'])
                u['clip_alpha'] = min(u['clip_alpha'], rec['clip_alpha'])
                # 将边列表拓展（若需要追踪多个边，可扩展，这里保留第一个）
                merged = True
                break
        if not merged:
            unique_recs.append(rec)
    inter_records = unique_recs

    # 按边分组并插入（在每条边上按 alpha 排序）
    def insert_into(poly_nodes: List[List[Node]], key_prefix: str):
        grouped: Dict[tuple, List[dict]] = {}
        for rec in inter_records:
            edge = rec[f'{key_prefix}_edge']
            grouped.setdefault(edge, []).append(rec)

        for edge, recs in grouped.items():
            ring_idx, start_idx, end_idx = edge
            nodes = poly_nodes[ring_idx]
            # 找到 start vertex 在 nodes 中的位置（原始顶点 edge 里 start_idx）
            insert_pos = None
            for idx, node in enumerate(nodes):
                # 原始顶点的 edge 存为 (ring_idx, vertex_index, next_index)
                if (not node.is_inter) and node.edge[1] == start_idx:
                    insert_pos = idx + 1
                    break
            if insert_pos is None:
                insert_pos = len(nodes)

            alpha_key = f'{key_prefix}_alpha'
            recs_sorted = sorted(recs, key=lambda r: (
                r[alpha_key], r['pt'][0], r['pt'][1]))

            # 逐个插入（合并近似相同点）
            for rec in recs_sorted:
                pt = rec['pt']
                alpha = rec[alpha_key]
                # 全环搜索是否已有非常接近的交点（避免重复）
                found_idx = None
                for k, nnode in enumerate(nodes):
                    if nnode.is_inter and point_eq(nnode.pt, pt):
                        found_idx = k
                        # 更新 alpha 与 edge 信息（以便排序/追踪）
                        if nnode.alpha is None or alpha < nnode.alpha:
                            nnode.alpha = alpha
                            nnode.edge = edge
                        break
                if found_idx is not None:
                    # 已有交点，无需插入
                    continue
                # 否则插入新节点
                new_node = Node(pt=pt, is_inter=True, alpha=alpha, edge=edge)
                nodes.insert(insert_pos, new_node)
                insert_pos += 1

    insert_into(subj_nodes, 'subj')
    insert_into(clip_nodes, 'clip')

    # 建立 neighbor 链接（通过坐标匹配）
    def find_inter_node(poly_nodes: List[List[Node]], pt) -> Optional[Node]:
        for ring in poly_nodes:
            for node in ring:
                if node.is_inter and point_eq(node.pt, pt):
                    return node
        return None

    for rec in inter_records:
        pt = rec['pt']
        node_s = find_inter_node(subj_nodes, pt)
        node_c = find_inter_node(clip_nodes, pt)
        if node_s is None or node_c is None:
            continue
        node_s.neighbor = node_c
        node_c.neighbor = node_s
    return subj_nodes, clip_nodes


def mark_entry_exit(subj_nodes: List[List[Node]], clip_nodes: List[List[Node]],
                    subject: PolygonModel, clipper: PolygonModel):
    """
    对主多边形（subj_nodes）上的每个交点判断是否为入点。
    判定方法：在交点沿主多边形前进一个很小步长的 probe 点，若 probe 在 clipper 内 -> 交点为入点。
    使用相对偏移（基于后继点的边长）代替绝对偏移以增强数值鲁棒性。
    """
    for ring_idx, nodes in enumerate(subj_nodes):
        n = len(nodes)
        if n == 0:
            continue
        for i, node in enumerate(nodes):
            if not node.is_inter:
                continue
            if node.is_entry is not None:
                continue

            # 找到交点后的一个有效点方向（后继第一个不同点）
            next_idx = None
            for k in range(1, n):
                cand = nodes[(i + k) % n]
                if not point_eq(cand.pt, node.pt):
                    next_idx = (i + k) % n
                    break
            # 若后继没有找到（退化），尝试前一个
            if next_idx is None:
                for k in range(1, n):
                    cand = nodes[(i - k) % n]
                    if not point_eq(cand.pt, node.pt):
                        next_idx = (i - k) % n
                        break
                if next_idx is None:
                    # 无法判定（孤立点）
                    continue

            next_pt = nodes[next_idx].pt
            dx = next_pt[0] - node.pt[0]
            dy = next_pt[1] - node.pt[1]
            norm = math.hypot(dx, dy)
            if norm < EPS:
                # 方向退化，直接把 probe 定为 node.pt 的微移（ fallback ）
                ux, uy = 1.0, 0.0
                offset = EPS * 100.0
            else:
                ux = dx / norm
                uy = dy / norm
                # 相对偏移：edge length * 1e-4，保证在边内且不会太小
                offset = max(EPS * 10.0, norm * 1e-4)

            probe = (node.pt[0] + ux * offset, node.pt[1] + uy * offset)
            inside = point_in_polygon_with_holes(probe, clipper)
            node.is_entry = True if inside else False
            if node.neighbor is not None:
                node.neighbor.is_entry = not node.is_entry


def build_results_from_nodes(subj_nodes: List[List[Node]], clip_nodes: List[List[Node]]) -> List[Ring]:
    """
    按 Weiler-Atherton 跟踪规则从未访问交点开始构造结果环。
    返回 ring 列表（每个 ring 是点序列）。
    """
    results: List[Ring] = []

    # 收集主侧的交点作为起点池
    inter_nodes = [
        node for ring in subj_nodes for node in ring if node.is_inter]

    # helper: 在 nodes_struct 中找到 node 的 (ring_idx, idx)
    def find_idx(node: Node, nodes_struct: List[List[Node]]):
        for r_idx, ring in enumerate(nodes_struct):
            for idx, nd in enumerate(ring):
                if nd is node:
                    return r_idx, idx
        return None, None

    for start_node in inter_nodes:
        if start_node.visited:
            continue
        if start_node.neighbor is None:
            # 孤立交点，标记并跳过
            start_node.visited = True
            continue

        current = start_node
        current_side = 'subj' if current.is_entry else 'clip'

        polygon_pts: List[Point] = []
        polygon_pts.append(current.pt)

        safety = 0
        while True:
            safety += 1
            if safety > 100000:
                break

            if current_side == 'subj':
                r_idx, i_idx = find_idx(current, subj_nodes)
                if r_idx is None:
                    # 无法在 subj 上找到，切换侧
                    current_side = 'clip'
                    continue
                nodes = subj_nodes[r_idx]
                n = len(nodes)
                j = i_idx
                while True:
                    j = (j + 1) % n
                    node = nodes[j]
                    if not point_eq(polygon_pts[-1], node.pt):
                        polygon_pts.append(node.pt)
                    if node.is_inter:
                        # 标记访问（仅在实际经过时）
                        node.visited = True
                        if node.neighbor:
                            node.neighbor.visited = True
                            current = node.neighbor
                        else:
                            current = node
                        current_side = 'clip'
                        break
                    # 防止无限循环（如果回到起点）
                    if j == i_idx:
                        break

            else:
                r_idx, i_idx = find_idx(current, clip_nodes)
                if r_idx is None:
                    current_side = 'subj'
                    continue
                nodes = clip_nodes[r_idx]
                n = len(nodes)
                j = i_idx
                while True:
                    j = (j + 1) % n
                    node = nodes[j]
                    if not point_eq(polygon_pts[-1], node.pt):
                        polygon_pts.append(node.pt)
                    if node.is_inter:
                        node.visited = True
                        if node.neighbor:
                            node.neighbor.visited = True
                            current = node.neighbor
                        else:
                            current = node
                        current_side = 'subj'
                        break
                    if j == i_idx:
                        break

            # 结束条件：回到起点交点（坐标相同或对象相同且已访问）
            if point_eq(polygon_pts[0], polygon_pts[-1]) or (current is start_node and current.visited):
                if len(polygon_pts) >= 2 and point_eq(polygon_pts[0], polygon_pts[-1]):
                    polygon_pts = polygon_pts[:-1]
                break

        # 清理并加入结果（去除相邻重复点）
        cleaned = []
        for p in polygon_pts:
            if not cleaned or not point_eq(cleaned[-1], p):
                cleaned.append(p)
        if len(cleaned) >= 3:
            results.append(cleaned)

    # 打印结果环信息
    print("结果环信息:")
    for idx, ring in enumerate(results):
        print(f"  环 {idx+1} (共 {len(ring)} 个点):")
        for pt in ring:
            print(f"    {pt}")

    return results


def weiler_atherton_clip(subject: PolygonModel, clipper: PolygonModel) -> List[Ring]:
    """
    计算 subject ∩ clipper 并以环列表返回。
    若没有交点则做包含性判断（subject 在 clipper 内 -> 返回 subject；clipper 在 subject 内 -> 返回 clipper）。
    """
    if subject is None or clipper is None:
        return []

    subj_nodes, clip_nodes = insert_intersections(subject, clipper)

    # 判断是否有交点
    has_inter = any(node.is_inter for ring in subj_nodes for node in ring)
    if not has_inter:
        # 无交点：判断包含关系（用外环第一个点做代表）
        if subject.rings and subject.rings[0]:
            rep = subject.rings[0][0]
            if point_in_polygon_with_holes(rep, clipper):
                return [list(r) for r in subject.rings]
        if clipper.rings and clipper.rings[0]:
            rep2 = clipper.rings[0][0]
            if point_in_polygon_with_holes(rep2, subject):
                return [list(r) for r in clipper.rings]
        return []

    # 标记入/出点
    mark_entry_exit(subj_nodes, clip_nodes, subject, clipper)

    # 按规则跟踪生成结果环
    results = build_results_from_nodes(subj_nodes, clip_nodes)

    return results
