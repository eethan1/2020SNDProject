from catknight import *
def myCatknight():
    topo = Catknight(auth=('...','...'))
    nodes = ['a', 'b', 'c']
    links = [('a','b'),('b','c')]
    # links = []
    net = topo.feed(nodes, links)
    topo.addArps()
    topo.addPath(['a','b','c'])
    topo.addPath(['c','b','a'])
    CLI(net)

myCatknight()
