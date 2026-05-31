####################################################
# LSrouter.py
# Name: Phan Thị Hương Giang
# HUID: 24022644
#####################################################

import json
from router import Router
from packet import Packet


class LSrouter(Router):
    """Link state routing protocol implementation.

    Add your own class fields and initialization code (e.g. to create forwarding table
    data structures). See the `Router` base class for docstrings of the methods to
    override.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Initialize base class - DO NOT REMOVE
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        
        #Bảng định tuyến: dst_addr -> (cost, port)
        self.forwarding_table = {}

        #Lưu các kết nối trực tiếp của chính router này
        self.link_costs = {} #port -> cost
        self.endpoints = {} #port -> endpoint_addr

        # Cấu trúc link-state 
        #topology lưu bản đồ toàn mạng : node -> {neighbor: cost}
        self.topology = {self.addr: {}}
        self.seq_nums = {} #node-> seq lớn nhất từng nhận
        self.my_seq_num = 0 #seq của bản thân tăng mỗi thay đổi

    def broadcast_ls(self):
        """Phát thanh Link-State của chính mình cho toàn mạng"""
        self.my_seq_num += 1
        
        # Đóng gói thông tin: Ai gửi? Số thứ tự bao nhiêu? Láng giềng là ai?
        message = {
            "origin": self.addr,
            "seq_num": self.my_seq_num,
            "links": self.topology[self.addr]
        }
        content = json.dumps(message)
        
        # Gửi cho tất cả hàng xóm
        for port, endpoint in self.endpoints.items():
            packet = Packet(Packet.ROUTING, self.addr, endpoint)
            packet.content = content
            self.send(port, packet)

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        # TODO
        if packet.is_traceroute:
            if packet.dst_addr in self.forwarding_table:
                cost, target_port = self.forwarding_table[packet.dst_addr]
                if target_port is not None:
                    self.send(target_port,packet)
        else:
            try:
                # Mở gói tin JSON
                import json
                data = json.loads(packet.content)
                origin = data["origin"]
                seq_num = data["seq_num"]
                links = data["links"]

                #bỏ qua nếu là gói tin do chính mình tạo ra trong quá khứ
                if origin == self.addr:
                    return
                
                #kiểm tra seq: chỉ xử lí seq_num lớn hơn số đã lưu
                if seq_num > self.seq_nums.get(origin, -1):
                    # 1. Update the local copy of the link state
                    self.seq_nums[origin] = seq_num
                    self.topology[origin] = links

                    # 2. Update the forwarding table (Chạy thuật toán Dijkstra)
                    self.recompute_dijkstra()

                    # 3. Broadcast the packet to other neighbors (Lan truyền/Flooding)
                    for neighbor_port, endpoint in self.endpoints.items():
                        # Gửi cho tất cả hàng xóm, NGOẠI TRỪ cổng vừa nhận được gói tin này
                        if neighbor_port != port:
                            # Tạo bản sao của gói tin để forward
                            from packet import Packet
                            forward_packet = Packet(Packet.ROUTING, self.addr, endpoint)
                            forward_packet.content = packet.content # Giữ nguyên nội dung gốc
                            self.send(neighbor_port, forward_packet)
            
            except Exception:
                # Bỏ qua nếu gói tin bị lỗi định dạng
                pass



    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        self.link_costs[port] = cost
        self.endpoints[port] = endpoint
        self.topology[self.addr][endpoint] = cost
        self.broadcast_ls()
        self.recompute_dijkstra()

    def handle_remove_link(self, port):
        """Handle removed link."""
        if port in self.endpoints:
            endpoint = self.endpoints[port]
            del self.endpoints[port]
            del self.link_costs[port]
            if endpoint in self.topology[self.addr]:
                del self.topology[self.addr][endpoint]
        
        self.broadcast_ls()
        self.recompute_dijkstra()

    def handle_time(self, time_ms):
        """Handle current time."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_ls()
    
    def recompute_dijkstra(self):
        """Tính toán lại bảng định tuyến bằng thuật toán Dijkstra"""
        # 1. Thu thập tất cả các node hiện có trong bản đồ (topology)
        nodes = set(self.topology.keys())
        for neighbors in self.topology.values():
            nodes.update(neighbors.keys())

        # 2. Khởi tạo bảng khoảng cách và node liền trước (để truy vết đường đi)
        distances = {node: float('inf') for node in nodes}
        distances[self.addr] = 0
        
        # Biến previous dùng để lưu dấu vết: để đến được node này thì bước trước đó là node nào?
        previous = {node: None for node in nodes}
        
        unvisited = set(nodes)

        # 3. Vòng lặp chính của Dijkstra
        while unvisited:
            # Tìm node có khoảng cách nhỏ nhất trong số các node chưa thăm
            current_node = min(unvisited, key=lambda node: distances[node])
            
            # Nếu node gần nhất mà cũng bằng vô cực -> các node còn lại không thể tới được (mạng bị đứt đoạn)
            if distances[current_node] == float('inf'):
                break 
                
            unvisited.remove(current_node)

            # Cập nhật khoảng cách tới các hàng xóm của current_node
            if current_node in self.topology:
                for neighbor, cost in self.topology[current_node].items():
                    if neighbor in unvisited:
                        new_dist = distances[current_node] + cost
                        if new_dist < distances[neighbor]:
                            distances[neighbor] = new_dist
                            previous[neighbor] = current_node # Lưu lại dấu vết

        # 4. Từ kết quả Dijkstra, xây dựng lại forwarding_table (Đích đến -> (Chi phí, Cổng))
        new_forwarding_table = {}
        for dst in nodes:
            # Bỏ qua chính mình và các node không thể tới được
            if dst != self.addr and distances[dst] < float('inf'):
                
                # Truy vết ngược từ Đích (dst) về Nguồn (self.addr) để tìm hàng xóm đầu tiên (first_hop)
                curr = dst
                while previous[curr] != self.addr:
                    curr = previous[curr]
                
                first_hop_neighbor = curr
                
                # Tìm xem hàng xóm đầu tiên này đang cắm vào cổng (port) nào của router
                best_port = None
                for port, endpoint in self.endpoints.items():
                    if endpoint == first_hop_neighbor:
                        best_port = port
                        break
                
                # Nếu tìm thấy cổng, lưu vào bảng định tuyến
                if best_port is not None:
                    new_forwarding_table[dst] = (distances[dst], best_port)

        # Cập nhật bảng định tuyến mới
        self.forwarding_table = new_forwarding_table

    def __repr__(self):
        """Representation for debugging in the network visualizer."""
        return f"LSrouter({self.addr}) | Seq: {self.my_seq_num} | Table: {self.forwarding_table}"