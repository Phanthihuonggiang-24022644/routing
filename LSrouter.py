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
    #Khi một router được tạo ra nó cần biết mình là ai, biết hàng xóm, có bản đồ mạng, bảng định tuyến...
    # Tạo một router mới có addr: tên router(A,B,C...), heartbeat_time: thời gian định kì gửi thông tin mạng
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  #gọi constructor của lớp cha-> router có sẵn địa chỉ(self.addr), khả năng gửi pkt(send), cơ chế mạng mô phỏng
        self.heartbeat_time = heartbeat_time #khai báo thời gian bao lâu sẽ thông báo tình trạng mạng 1 lần
        self.last_time = 0 # lần cuối router gửi thông tin mạng
        #Nếu (now - last_time >= heartbeat_time -> gửi lại ls)
        
        #Bảng định tuyến: dst_addr -> (cost, port) ví dụ {"D": (3,port0)}
        #Chức năng là giúp router biết muốn đi đến D thì phải gửi qua port0 mất cost = 3
        self.forwarding_table = {}

        #Lưu các kết nối trực tiếp của chính router này
        self.link_costs = {} #port -> cost : nếu từ cổng này thì tốn bao nhiêu để tới hàng xóm, biết được đường đi này tốn bao nhiêu
        self.endpoints = {} #port -> endpoint_addr : đường đi này tới ai

        # Cấu trúc link-state 
        #topology lưu bản đồ toàn mạng : node -> {neighbor: cost}
        self.topology = {self.addr: {}}
        self.seq_nums = {} #node-> seq lớn nhất từng nhận
        #vd khi router nhận được thông tin 3 lần từ A thì nó sẽ lưu = 3 để biết đấy là thông tin mới nhất đc cập nhật
        #để tránh update sai dữ liệu
        self.my_seq_num = 0 #seq của bản thân tăng mỗi thay đổi-> tôi cập nhật mạng lần thứ n

    def broadcast_ls(self):
        """Phát thanh Link-State của chính mình cho toàn mạng"""
        """Router thông báo tình trạng kết nối của mình"""
        self.my_seq_num += 1 #mỗi lần cập nhật thì tăng số phiên bản cập nhật lên 1
        
        # Đóng gói thông tin trạng thái của mạng: Ai gửi?phiên bản thông tin mới hay cũ,đang nối với ai, chi phí bao nhiêu
        message = {
            "origin": self.addr,
            "seq_num": self.my_seq_num,
            "links": self.topology[self.addr]
        }
        content = json.dumps(message)
        #đóng gói dữ liệu để gửi đi dictionary-> string
        
        # Gửi cho tất cả hàng xóm
        for port, endpoint in self.endpoints.items():
            packet = Packet(Packet.ROUTING, self.addr, endpoint) #tạo một packet thông tin mạng,ai gửi, gửi ai
            packet.content = content #thông tin mạng
            self.send(port, packet) #gửi từng packet qua đúng port
    #Mỗi khi có gói tin vào port, hàm sẽ nhận, kiểm tra xem đó là gói tin gì và quyết định làm gì tiếp
    def handle_packet(self, port, packet):
        """Process incoming packet."""
        # Nếu đây là gói tin data bình thường
        if packet.is_traceroute:
            if packet.dst_addr in self.forwarding_table: #kiểm tra đc đích có tồn tại trong bảng định tuyến ch
                cost, target_port = self.forwarding_table[packet.dst_addr] #gán chi phí, cổng đích
                if target_port is not None: #nếu port đích thật sự tồn tại thì gửi packet đến cổng đích
                    self.send(target_port,packet)
        else:
            try:
                # Mở gói tin JSON
                import json #thư viện xử lý văn bản
                data = json.loads(packet.content) #biến content từ chuỗi JSON thành dictionary của python vào biến data để dễ thao tác
                origin = data["origin"] #tên router đầu tiên gửi tin này
                seq_num = data["seq_num"] #số thứ tự phiên bản để biết tin cũ hay mới
                links = data["links"] #danh sách láng giềng của router

                #bỏ qua nếu là gói tin do chính mình tạo ra trong quá khứ
                if origin == self.addr:
                    return
                
                #kiểm tra seq: chỉ xử lí seq_num lớn hơn số đã lưu
                #.get(origin, -1) là tìm số thứ tự trong seq_nums nếu mà không có thì mặc định là -1
                if seq_num > self.seq_nums.get(origin, -1):
                    # 1. Cập nhật bản đồ 
                    self.seq_nums[origin] = seq_num # cập nhật phiên bản mới nhất của thông tin
                    self.topology[origin] = links # cập nhật bản đồ mạng 

                    # 2. Update the forwarding table (Chạy thuật toán Dijkstra tìm đường đi ngắn nhất)
                    self.recompute_dijkstra()

                    # 3. Broadcast the packet to other neighbors
                    for neighbor_port, endpoint in self.endpoints.items():
                        # Gửi cho tất cả hàng xóm, NGOẠI TRỪ cổng vừa nhận được gói tin này để tránh gửi lại người vừa gửi
                        if neighbor_port != port:
                            # Tạo bản sao của gói tin để forward
                            from packet import Packet
                            forward_packet = Packet(Packet.ROUTING, self.addr, endpoint)
                            forward_packet.content = packet.content # Giữ nguyên nội dung gốc đổi người gửi
                            self.send(neighbor_port, forward_packet)
            
            except Exception:
                # Bỏ qua nếu gói tin bị lỗi định dạng
                pass


    # Khi có link mới vào router           
    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        self.link_costs[port] = cost #chi phí cổng mới
        self.endpoints[port] = endpoint # tên router ở đầu bên kia
        self.topology[self.addr][endpoint] = cost # cập nhật bản đồ thêm 1 link mới 
        self.broadcast_ls() # thông báo cho toàn mạng về thay đổi
        self.recompute_dijkstra() # tính lại đường đi ngắn nhất

    #Khi port bị mất kết nối ( chỉ biết port nào bị đứt k biết nó nói đi đâu) thì rút dây ở cổng port ra khỏi router
    def handle_remove_link(self, port):
        """Handle removed link."""
        if port in self.endpoints: #Kiểm tra xem trước đó có thực sự nối với ai không
            endpoint = self.endpoints[port] #tìm xem port đó đang nối đến neighbor nào
            del self.endpoints[port] #xóa endpoint và cost ra khỏi router
            del self.link_costs[port]
            if endpoint in self.topology[self.addr]: #cập nhật bản đồ xóa link vừa mất đi
                del self.topology[self.addr][endpoint]
        
        self.broadcast_ls() #thông báo cho hàng xóm 
        self.recompute_dijkstra() #tính lại đường đi

    # Gửi lại trạng thái sau 1 thời gian nhất định
    def handle_time(self, time_ms):
        """Handle current time."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_ls()
    
    def recompute_dijkstra(self):
        """Tính toán lại bảng định tuyến bằng thuật toán Dijkstra"""
        # 1. Thu thập tất cả các node hiện có trong bản đồ (topology)
        nodes = set(self.topology.keys()) # tạo 1 tập hợp chứa tất cả các router trong bản đồ
        for neighbors in self.topology.values(): # duyệt từng neighbor lấy cả hàng xóm của hàng xóm (có những router ch phát bản tin nhưng được liệt kê là neigbor)
            nodes.update(neighbors.keys())

        # 2. Khởi tạo bảng khoảng cách và node liền trước (để truy vết đường đi)
        distances = {node: float('inf') for node in nodes} # gán distances của mỗi node = vô cùng
        distances[self.addr] = 0 # distance đến nó thì = 0
        
        # Biến previous dùng để lưu dấu vết: để đến được node này thì bước trước đó là node nào?
        previous = {node: None for node in nodes}
        
        unvisited = set(nodes) #tạo danh sách node ch dc thăm

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
                for neighbor, cost in self.topology[current_node].items(): #duyệt qua từng hàm xóm của current_node
                    if neighbor in unvisited:
                        new_dist = distances[current_node] + cost # = cost từ nhà đến current_node + current_node -> neighbor
                        if new_dist < distances[neighbor]:
                            distances[neighbor] = new_dist
                            previous[neighbor] = current_node # Lưu lại dấu vết

        # 4. Từ kết quả Dijkstra, xây dựng lại forwarding_table (Đích đến -> (Chi phí, Cổng))
        new_forwarding_table = {}
        for dst in nodes: #xét từng node trong mạng
            # Bỏ qua chính mình và các node không thể tới được
            if dst != self.addr and distances[dst] < float('inf'):
                
                # Truy vết ngược từ Đích (dst) về Nguồn (self.addr) để tìm hàng xóm đầu tiên (first_hop)
                curr = dst
                while previous[curr] != self.addr:
                    curr = previous[curr]
                
                first_hop_neighbor = curr #node đầu tiên phải đi qua
                
                # Tìm xem hàng xóm đầu tiên này đang cắm vào cổng (port) nào của router
                best_port = None
                for port, endpoint in self.endpoints.items(): #duyệt qua tất cả port của router
                    if endpoint == first_hop_neighbor:
                        best_port = port
                        break
                
                # Nếu tìm thấy cổng, lưu vào bảng định tuyến
                if best_port is not None:
                    new_forwarding_table[dst] = (distances[dst], best_port)

        # Cập nhật bảng định tuyến mới
        self.forwarding_table = new_forwarding_table

    #Khi in ra object LSRouter sẽ hiển thị như thế nào, số thứ tự bản tin router, bảng định tuyến của nó
    def __repr__(self):
        """Representation for debugging in the network visualizer."""
        return f"LSrouter({self.addr}) | Seq: {self.my_seq_num} | Table: {self.forwarding_table}"