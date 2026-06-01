####################################################
# DVrouter.py
# Name:Phan Thị Hương Giang
# HUID:24022644
#####################################################
import json #dùng biến dữ liệu thành chuỗi và ngược lại
from router import Router
from packet import Packet #tạo packet gửi gói tin

class DVrouter(Router):
    """Distance vector routing protocol implementation.

    Add your own class fields and initialization code (e.g. to create forwarding table
    data structures). See the `Router` base class for docstrings of the methods to
    override.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Initialize base class - DO NOT REMOVE
        self.heartbeat_time = heartbeat_time #thời gian bao lâu router gửi thông tin cho hàng xóm
        self.last_time = 0 #lần cuối gửi thông tin 
        self.INFINITY = 16 #Gioi han cost max 
        #Bảng định tuyến cốt lõi : địa chỉ -> (cost,port)
        self.forwarding_table = {self.addr: (0,None)}

        #Lưu trữ trạng thái mạng phần cứng
        self.link_costs ={} #Cổng port -> chi phí(cost)
        self.endpoints = {} # port -> địa chỉ đầu bên kia
        
        #Lưu lại bản đồ mà hàng xóm nói cho
        # port -> {destination_addr: cost}
        self.neighbor_dvs = {} 

    #Tìm đường đi ngắn nhất tới mọi node
    def recompute(self):
        """"Tính lại bảng định tuyến từ đầu"""
        new_table = {self.addr: (0, None)}

        #Tập hợp tất cả các đích đến mà mạng có thể biết  
        destinations = set() #tạo tập rỗng chứa các đích
        destinations.update(self.endpoints.values()) #thêm các neighbors kết nối trực tiếp 
        #duyệt qua từng bảng định tuyến của neighbors lấy tất cả các node neighbor biết
        for dv in self.neighbor_dvs.values():
            destinations.update(dv.keys())
    
        #Tìm đường đi rẻ nhất cho từng destination
        for dst in destinations:
            if dst == self.addr:
                continue

            min_cost = self.INFINITY
            best_port = None  

            #1. Nếu dst là neighbor thì dùng luôn đường đó
            for port, endpoint in self.endpoints.items(): 
                if endpoint == dst:
                    cost = self.link_costs[port] #lấy chi phí trực tiếp qua cổng đó
                    if cost < min_cost:
                        min_cost = cost
                        best_port = port
    
            #2. Đi qua neighbor
            for port, dv in self.neighbor_dvs.items():
                # Nếu port có kết nối tới neighbor và neighbor biết đường tới dst
                if port in self.link_costs and dst in dv:
                    # Bỏ qua các link vô cực
                    if dv[dst] >= self.INFINITY:
                        continue

                    # cost = từ source-> neighbor + từ neighbor-> dst
                    cost = self.link_costs[port] + dv[dst]
                
                    #chọn đường đi ngắn nhất
                    if cost < min_cost:
                        min_cost = cost
                        best_port = port

            # Nếu tìm được đường đi thực tế(<vô cực) lưu vào bảng
            if min_cost < self.INFINITY:
                new_table[dst] = (min_cost, best_port)
    
        #So sánh bảng mới và cũ nếu có sự thay đổi(đứt cáp/ tìm thấy đường tốt hơn)
        changed = (self.forwarding_table != new_table)
        self.forwarding_table = new_table
        return changed
        
    #Gửi bảng định tuyến thông báo kết quả tính toán cho neighbor
    def broadcast_dv(self):
        """Gửi bảng DV cho tất cả neighbor"""
        for port,endpoint in self.endpoints.items(): #duyệt qua tất cả hàng xóm
            dv_to_send = {} #tạo bảng định tuyến gửi
            #duyệt toàn bộ bảng định tuyến
            for dst, (cost,next_hop) in self.forwarding_table.items():
            #Nếu đi đến đích phải mượn neighbor thì sẽ nói dối không biết đường đến đích để tránh lặp
            #next_hop : cổng mà router đang dùng để đi tới đích
            #port : cổng của neighbor mà ta sắp gửi DV
            #vd A->B->D mà B->D bị mất mà B vẫn tưởng A->D được thì nó sẽ tạo đường B->A->D
                if next_hop == port:
                    dv_to_send[dst] = self.INFINITY
                else:
                    dv_to_send[dst] = cost

            #Đóng gói thành chuỗi JSON và gửi pkt chứa thông tin mạng,nguồn,đích
            packet = Packet(Packet.ROUTING,self.addr, endpoint)
            packet.content = json.dumps(dv_to_send) #chuyển dict thành string để gửi
            self.send(port, packet)    
        

        #Hàm quyết định packet là data hay thông tin định tuyến và xử lý tương ứng
    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.is_traceroute: #là normal data packet 
            if packet.dst_addr in self.forwarding_table:
                cost, target_port = self.forwarding_table[packet.dst_addr]
                if cost < self.INFINITY and target_port is not None:
                    self.send(target_port, packet)
        else:
            #Nếu là routing packet của neighbor , mở gói tin và cập nhật bộ nhớ
            #nhận dv-> lưu dv -> recompute(đọc neighbor_dvs -> tính lại fowarding_table-> so sánh bảng cũ)-> thay đổi thì gửi dv mới
            try:
                neighbor_dv = json.loads(packet.content)
                self.neighbor_dvs[port] = neighbor_dv

                # LUÔN recompute
                if self.recompute():
                    self.broadcast_dv()

            except Exception:
                pass


    def handle_new_link(self, port, endpoint, cost):#object,cổng kết nối với neighbor,dc nb,cost của link
        """Handle new link."""
        self.link_costs[port] = cost
        self.endpoints[port] = endpoint
        self.neighbor_dvs[port] = {endpoint: 0} #Vì một router luôn biết đường tới chính nó với cost 0.
        if self.recompute():
            self.broadcast_dv()
        
    #hàm được gọi khi có một kết nối bị mất vd dây mạng bị đứt, node tắt hoặc link bị timeout
    def handle_remove_link(self, port):
        """Handle removed link."""
        # Xóa mọi ký ức về cổng đã chết
        if port in self.link_costs:
            del self.link_costs[port]
        if port in self.endpoints:
            del self.endpoints[port]
        if port in self.neighbor_dvs:
            del self.neighbor_dvs[port]
            
        # Bắt buộc tính lại bảng, nếu rớt mất đường đi thì báo cho các hàng xóm còn lại
        if self.recompute():
            self.broadcast_dv()

    def handle_time(self, time_ms):
        """Handle current time."""
        # Nhịp tim: Đến giờ thì gửi DV cho hàng xóm dù mạng không có gì thay đổi
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_dv()
        
    def __repr__(self):
        """Representation for debugging in the network visualizer."""
        # TODO
        #   NOTE This method is for your own convenience and will not be graded
        return f"DVrouter(addr={self.addr})"
