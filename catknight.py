import subprocess

from mininet.net import Mininet
from mininet.node import Node, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.util import macColonHex

import time
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
ETH_IPV4 = 2048
ETH_ARP = 2054

def int2dpid(dpid):
    try:
        dpid = hex(dpid)[2:]
        dpid = '0' * (16-len(dpid)) + dpid
        return dpid
    except IndexError:
        return Exception('Dpi failed: '+dpid)

class MininetTopo(object):
    def __init__(self):
        self.mac_decimal = 1

    def _new_mac(self):
        mac = macColonHex(self.mac_decimal)
        self.mac_decimal = self.mac_decimal +1
        return mac


class Catknight(MininetTopo):
    def __init__(self, auth):
        super(Catknight, self).__init__()
        self.s = requests.session()
        self.s.auth = auth
        # s.proxies = {'https':'socks4:127.0.0.1:8081'}
        self.s.verify = False
        self.flow_entries = []

    # nodes are list of names ['s1', 's2']
    # links are list of tuple of names [('s1', 's2'),...]
    # Every nodes will add two hosts, 10.0.i.1 and 10.0.i.2
    def feed(self, nodes=[], links=[]):
        self.nodes = nodes
        self.net = Mininet(topo=None, build=False, autoSetMacs=True)
        self.linkmap = {}
        self.switches = {}
        
        dpid_i = 7000
        ip_i = 1
        for node in nodes:
            self.switches[node] = {}
            self.switches[node]['obj'] = self.net.addSwitch(node, dpid=int2dpid(dpid_i), protocols='OpenFlow13', datapath='user',ovs='ovsk')
            # unused port number
            self.switches[node]['unused'] = 3
            self.switches[node]['dpid'] = dpid_i
            self.switches[node]['priority'] = 1000
            print(f'10.0.{ip_i}.0/24')
            self.switches[node]['host1'] = self.net.addHost(f"{node}_h1", ip=f'10.0.{ip_i}.1', mac=self._new_mac())
            self.switches[node]['host2'] = self.net.addHost(f"{node}_h2", ip=f'10.0.{ip_i}.2', mac=self._new_mac())
            ip_i = ip_i + 1
            self.net.addLink(self.switches[node]['obj'],self.switches[node]['host1'], port1=1, port2=1)
            self.net.addLink(self.switches[node]['obj'],self.switches[node]['host2'], port1=2, port2=1)
            dpid_i = dpid_i + 1



        for (a, b) in links:
            if a not in nodes or b not in nodes:
                raise Exception(f"link {a} or {b} not in nodes")
            self.net.addLink(
                self.switches[a]['obj'],
                self.switches[b]['obj'], 
                port1=self.switches[a]['unused'],
                port2=self.switches[b]['unused']
            )
            if self.linkmap.get(a) == None:
                self.linkmap[a] = {}
            if self.linkmap.get(b) == None:
                self.linkmap[b] = {}
            self.linkmap[a][b] = (self.switches[a]['unused'], self.switches[b]['unused'])
            self.linkmap[b][a] = (self.switches[b]['unused'], self.switches[a]['unused'])
            self.switches[a]['unused'] = self.switches[a]['unused'] + 1
            self.switches[b]['unused'] = self.switches[b]['unused'] + 1

        ctrl_1 = self.net.addController('c1', controller=RemoteController, ip='192.168.11.232', port=6633)
        self.net.build()
        for s in self.net.switches:
            s.start([ctrl_1])
        time.sleep(5)
        resp = self.s.get('https://192.168.11.232/api/openflow/switch/').json()
        for node in self.switches:
            for sw in resp:
                if self.switches[node]['dpid'] == sw['dpid']:
                    self.switches[node]['id'] = sw['id']
            print(f"{node}: {self.switches[node]['id']}")
        return self.net

    def addPath(self,path=[]):

        portl = []
        path1 = iter(path)
        path1.__next__()
        for (a,b) in zip(path, path1):
            if a not in self.linkmap or b not in self.linkmap[a]:
                raise Exception(f"One switches in Link {a} to {b} doesn't exist")
            

        ipv4_dst = self.switches[path[-1]]['host1'].IP()
        ipv4_src = self.switches[path[0]]['host1'].IP()
        fe = [{
            'sw' : self.switches[path[0]]['id'],
            'priority' : self.switches[path[0]]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': 1,
                'eth_type': ETH_IPV4,
                'ipv4_dst' : ipv4_dst,
                'ipv4_src' : ipv4_src
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : self.linkmap[path[0]][path[1]][0]
                },

            ],
            'groups' : 1
        },{
            'sw' : self.switches[path[-1]]['id'],
            'priority' : self.switches[path[-1]]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': self.linkmap[path[-2]][path[-1]][1],
                'eth_type': ETH_IPV4,
                'ipv4_dst' : ipv4_dst,
                'ipv4_src' : ipv4_src
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : 1
                },

            ],
            'groups' : 1
        },
        ]
        self.switches[path[0]]['priority'] = self.switches[path[0]]['priority'] + 1
        self.switches[path[-1]]['priority'] = self.switches[path[-1]]['priority'] + 1   
        for i in range(1,len(path)-1):
            fe.append({
            'sw' : self.switches[path[i]]['id'],
            'priority' : self.switches[path[i]]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': self.linkmap[path[i-1]][path[i]][1],
                'eth_type': ETH_IPV4,
                'ipv4_dst' : ipv4_dst,
                'ipv4_src' : ipv4_src
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : self.linkmap[path[i]][path[i+1]][0]
                },

            ],
            'groups' : 1
        })
            self.switches[path[i]]['priority'] = self.switches[path[i]]['priority'] + 1
        time.sleep(5)
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=fe).json()
        print(resp)
        self.flow_entries = self.flow_entries + resp


    def addLanRoute(self):
        fe = []
        node = 'a'
        print(f"IP {self.switches[node]['host1'].IP()} {self.switches[node]['host2'].IP()}")
        fe.append({
            'sw' : self.switches[node]['id'],
            'priority' : self.switches[node]['priority'],
            'table_id': 1,
            'match' : {
                'in_port' : 1,
                'eth_type': ETH_IPV4,
                'ipv4_dst': self.switches[node]['host2'].IP(),
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : 2,
                },
            ],
            'groups' : 1
        })
        self.switches[node]['priority'] = self.switches[node]['priority'] + 1
        fe.append({
            'sw' : self.switches[node]['id'],
            'priority' : self.switches[node]['priority'],
            'table_id': 1,
            'match' : {
                'in_port': 2,
                'eth_type': ETH_IPV4,
                'ipv4_dst': self.switches[node]['host1'].IP(),
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : 1,
                },
            ],
            'groups' : 1
        })
        self.switches[node]['priority'] = self.switches[node]['priority'] + 1
        print(fe)
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=fe)
        print(resp.json())
        self.flow_entries = self.flow_entries + resp.json()
        return resp


    def addArps(self):
        fe = []
        for node in self.switches:
            fe.append({
                'sw' : self.switches[node]['id'],
                'priority' : self.switches[node]['priority'],
                'table_id' : 1,
                'match' : {
                    'eth_type': ETH_ARP
                },
                'actions' : [
                    {
                        'type': 'OUTPUT',
                        'port' : 'FLOOD',
                    },
                ],
                'groups' : 1
            })
            self.switches[node]['priority'] = self.switches[node]['priority'] + 1
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=fe).json()
        print(resp)
        self.flow_entries = self.flow_entries + resp
        return resp

    def test(self):
        self.net = Mininet(topo=None, build=False, autoSetMacs=True)

        print('create switches')
        s101 = self.net.addSwitch('s101', dpid=int2dpid(101), protocols='OpenFlow13', datapath='user',ovs='ovsk')
        s102 = self.net.addSwitch('s102', dpid=int2dpid(102), protocols='OpenFlow13', datapath='user',ovs='ovsk')
        s103 = self.net.addSwitch('s103', dpid=int2dpid(103), protocols='OpenFlow13', datapath='user',ovs='ovsk')
        h1 = self.net.addHost('s101_h1', ip='10.0.1.1/24', mac=self._new_mac(), defaultRoute='via 10.0.1.254')
        h2 = self.net.addHost('s101_h2', ip='10.0.1.2/24', mac=self._new_mac(), defaultRoute='via 10.0.1.254')
        self.net.addLink(s101, h1, port1=1, port2=1)
        self.net.addLink(s101, h2, port1=2, port2=1)
        ctrl_1 = self.net.addController('c1', controller=RemoteController, ip='192.168.11.232', port=6633)
        self.net.build()

        for s in self.net.switches:
            s.start([ctrl_1])

        return self.net

    def delete(self):
        self.net.stop()

    def __del__(self):
        if self.net != None:
            self.net.stop()
        if hasattr(self, 'flow_entries'):
            for i in self.flow_entries:
                resp = self.s.delete(f'https://192.168.11.232/api/openflow/flowentry/{i["id"]}/')
                print(f"{i['id']}: {resp.text}")
        








