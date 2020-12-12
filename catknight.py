import subprocess

from mininet.net import Mininet
from mininet.node import Node, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.util import macColonHex

import time
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from pprint import pprint
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


def NAPAfe(sw, priority, match, actions):
    return {
            'sw' : sw,
            'priority' : priority,
            'table_id' : 1,
            'match' : match,
            'actions' : actions,
            'groups' : 1
        }



logf = open('aaa.log', 'w') 
def printlog(text):
    if text == '\n':
        print()
        logf.write('\n')
        return
    pprint(text, stream=logf)
    print(text)


class Catknight(MininetTopo):
    def __init__(self, auth, dpid_i=7000, clean=True):
        super(Catknight, self).__init__()
        self.s = requests.session()
        self.s.auth = auth
        # s.proxies = {'https':'socks4:127.0.0.1:8081'}
        self.s.verify = False
        self.flow_entries = []
        self.dpid_i = dpid_i
        self.clean = clean

    def multioutputge(self, sw, gid, ports=[]):
        ports = list(set(ports))
        ge = {
            "sw":sw,
            "groups": 1,
            "group_id": gid,
            "buckets" : [],
            "type" : 'ALL',
            "level": 0
        }
        for port in ports:
            ge['buckets'].append({
                "actions": [{
                    "type": "OUTPUT",
                    "port" : port
                }],
                "weight": 0
             })
        return ge
    # nodes are list of names ['s1', 's2']
    # links are list of tuple of names [('s1', 's2'),...]
    # Every nodes will add two hosts, 10.0.i.1 and 10.0.i.2
    def feed(self, nodes=[], links=[]):
        self.nodes = nodes
        self.net = Mininet(topo=None, build=False, autoSetMacs=True)
        self.linkmap = {}
        self.switches = {}
        dpid_i = self.dpid_i
        ip_i = 1
        for node in nodes:
            self.switches[node] = {}
            self.switches[node]['obj'] = self.net.addSwitch(node, dpid=int2dpid(dpid_i), protocols='OpenFlow13', datapath='user',ovs='ovsk')
            # unused port number
            self.switches[node]['unused'] = 3
            self.switches[node]['dpid'] = dpid_i
            self.switches[node]['priority'] = 1000
            self.switches[node]['unused_gid'] = 1
            self.switches[node]['multioutput'] = {}
            printlog(f'10.0.{ip_i}.0/24')
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

        while 1:
            time.sleep(5)
            resp = self.s.get('https://192.168.11.232/api/openflow/switch/').json()
            printlog('Get switch info')
            printlog(resp)
            try:
                for node in self.switches:
                    for sw in resp:
                        if self.switches[node]['dpid'] == sw['dpid']:
                            self.switches[node]['id'] = sw['id']
                    printlog(f"{node}: {self.switches[node]['id']}")
                    printlog("\n")
            except:
                continue
            break
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
        # tail endpoint ipv4
        fe = [{
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
        self.switches[path[-1]]['priority'] = self.switches[path[-1]]['priority'] + 1  
        # head endpoint arp
        fe.append({
            'sw' : self.switches[path[0]]['id'],
            'priority' : self.switches[path[0]]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': 1,
                'eth_type': ETH_ARP,
                'arp_spa' : ipv4_src,
                'arp_tpa' : ipv4_dst
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : self.linkmap[path[0]][path[1]][0]
                },

            ],
            'groups' : 1
        })
        self.switches[path[0]]['priority'] = self.switches[path[0]]['priority'] + 1
        # tail endpoint arp
        fe.append({
            'sw' : self.switches[path[-1]]['id'],
            'priority' : self.switches[path[-1]]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': self.linkmap[path[-2]][path[-1]][1],
                'eth_type': ETH_ARP,
                'arp_spa' : ipv4_src,
                'arp_tpa' : ipv4_dst
            },
            'actions' : [
                {
                    'type': 'OUTPUT',
                    'port' : 1
                },

            ],
            'groups' : 1
        })
        self.switches[path[-1]]['priority'] = self.switches[path[-1]]['priority'] + 1
        # prepare group entry for multi path output
        print('Multioutput sw: '+ path[0])
        print(self.switches[path[0]]['multioutput'])
        if ipv4_dst not in self.switches[path[0]]['multioutput']:
            self.switches[path[0]]['multioutput'][ipv4_dst] = {}
            self.switches[path[0]]['multioutput'][ipv4_dst]['gid'] = self.switches[path[0]]['unused_gid']
            self.switches[path[0]]['unused_gid'] = self.switches[path[0]]['unused_gid'] + 1
            self.switches[path[0]]['multioutput'][ipv4_dst]['ports'] = []
            self.switches[path[0]]['multioutput'][ipv4_dst]['geid'] = ''
            self.switches[path[0]]['multioutput'][ipv4_dst]['feid'] = ''
            self.switches[path[0]]['multioutput'][ipv4_dst]['priority'] = self.switches[path[0]]['priority']
            self.switches[path[0]]['priority'] = self.switches[path[0]]['priority'] + 1

        if self.switches[path[0]]['multioutput'][ipv4_dst]['feid'] != '':
            resp = self.s.delete(f"https://192.168.11.232/api/openflow/flowentry/{self.switches[path[0]]['multioutput'][ipv4_dst]['feid']}/")
            self.switches[path[0]]['multioutput'][ipv4_dst]['feid'] = ''
            printlog('Delete head action group fe')
            printlog(resp)
        if self.switches[path[0]]['multioutput'][ipv4_dst]['geid'] != '' :
            resp = self.s.delete(f"https://192.168.11.232/api/openflow/groupentry/{self.switches[path[0]]['multioutput'][ipv4_dst]['geid']}/")
            printlog(f"Delete ge {self.switches[path[0]]['multioutput'][ipv4_dst]['geid']}")
            printlog(f"{resp.status_code}: {resp.text}" )
        self.switches[path[0]]['multioutput'][ipv4_dst]['ports'].append(self.linkmap[path[0]][path[1]][0])

        # add group entry
        fsw = self.switches[path[0]]
        ge = [self.multioutputge(fsw['id'], fsw['multioutput'][ipv4_dst]['gid'],fsw['multioutput'][ipv4_dst]['ports'])]
        printlog('Groupentry')
        printlog(ge)
        printlog('Try to Add group entry')
        while 1:
            try:
                resp = self.s.post('https://192.168.11.232/api/openflow/groupentry/',json=ge)
                print(self.switches[path[0]]['multioutput'][ipv4_dst]['geid'])
                printlog(resp.json())
                fsw['multioutput'][ipv4_dst]['geid'] = resp.json()[0]['id']
            except:
                time.sleep(10)
                continue
            break
 
        # add head action group flow entry

        hagfe = [{
            'sw' : self.switches[path[0]]['id'],
            'priority' : self.switches[path[0]]['multioutput'][ipv4_dst]['priority'],
            'table_id' : 1,
            'match' : {
                'in_port': 1,
                'eth_type': ETH_IPV4,
                'ipv4_dst' : ipv4_dst,
                'ipv4_src' : ipv4_src
            },
            'actions' : [
                {
                    'type': 'GROUP',
                    'group_id' : self.switches[path[0]]['multioutput'][ipv4_dst]['gid']
                },

            ],
            'groups' : 1
        }]
        printlog('Prepare head action group fe')
        printlog(hagfe)
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=hagfe).json()
        printlog("add head action group fe")
        printlog(resp)
        self.switches[path[0]]['multioutput'][ipv4_dst]['feid'] = resp[0]['id']


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
            fe.append({
                'sw' : self.switches[path[i]]['id'],
                'priority' : self.switches[path[i]]['priority'],
                'table_id' : 1,
                'match' : {
                    'in_port': self.linkmap[path[i-1]][path[i]][1],
                    'eth_type': ETH_ARP,
                    'arp_spa' : ipv4_src,
                    'arp_tpa' : ipv4_dst
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
        printlog('Flow entry')
        printlog(fe)
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=fe).json()
        printlog("add  Path")
        printlog(resp)
        printlog("\n")
        self.flow_entries = self.flow_entries + resp
        logf.flush()
    
    def cmd(self, node, command):
        print(self.switches[node]['host1'])
        self.switches[node]['host1'].cmdPrint(command) 

    def pingAll(self):
        print('pingAll')
        self.net.pingAll()

    def ping(self, n1, n2):
        h1 = self.switches[n1]['host1']
        h2 = self.switches[n2]['host1']
        print('ping')
        print(h1, h2)
        self.net.ping([h1, h2])
        


    def addLanRoute(self):
        fe = []
        node = 'a'
        (f"IP {self.switches[node]['host1'].IP()} {self.switches[node]['host2'].IP()}")
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
        printlog('Flowentry')
        printlog(fe)
        resp = self.s.post('https://192.168.11.232/api/openflow/flowentry/', json=fe)
        printlog(resp.json())
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
        printlog(resp)
        self.flow_entries = self.flow_entries + resp
        return resp

    def test(self):
        self.net = Mininet(topo=None, build=False, autoSetMacs=True)

        printlog('create switches')
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
        # if hasattr(self, 'flow_entries'):
        #     for i in self.flow_entries:
        #         resp = self.s.delete(f'https://192.168.11.232/api/openflow/flowentry/{i["id"]}/')
        #         printlog(f"{i['id']}: {resp.text}")
        # fes = self.s.get('https://192.168.11.232/api/openflow/flowentry/')
        # for i in fes.json():
        #     resp = self.s.delete(f'https://192.168.11.232/api/openflow/flowentry/{i["id"]}/')
        #     printlog(f"{i['id']}: {resp.text}")
        # time.sleep(5)
        if self.clean:
            sws = self.s.get('https://192.168.11.232/api/openflow/switch/').json()
            for sw in sws:
                resp = self.s.delete(f'https://192.168.11.232/api/openflow/switch/{sw["id"]}/')
                printlog(f"delete sw {sw['name']}: {resp.text}")
            time.sleep(5)
            resp = self.s.get(f'https://192.168.11.232/api/serve/rewrite_config')
            printlog(f"rewrite_config:")
            printlog(resp.text)
        logf.close()








