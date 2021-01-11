# 2020SNDProject

```
from catknight import *
def myCatknight():
    # add auth(account, password)
    topo = Catknight(auth=('...','...'))
    nodes = ['a', 'b', 'c']
    links = [('a','b'),('b','c')]
    # links = []
    net = topo.feed(nodes, links)
    topo.addPath(['a','b','c'])
    topo.addPath(['c','b','a'])
    CLI(net)

myCatknight()
```

## Catknight(auth, dpid_i=7000, clean=True)
- Parameters
    - auth `(username str, password str)`:  Authentication for NAPA
    - dpid_i `int`: The starting index for node dpid. 
    - clean `bool`: If true, destroy net when calling deconstructor.
- Returns
    - Catknight instance

### Class Method
#### feed(nodes=[],path=[])
- Parameters
    - nodes `[node1 str,node2 str...]`: List of nodes' name to build.
    - path `[(node1 str, node2 str)...]`: List of pair of connected node pairs. Each pair is a tuple of two nodes' name.  
- Returns
    - instance's `mininet.net.Mininet` object

#### addPath(path=[])
- Parameters
    - path `[str,str...]`: List of  nodes' name of a path. If some path have a common original node, the packet will have multiple forwarding packet at the node.
- Returns
    - None
