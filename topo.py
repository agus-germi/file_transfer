import argparse
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.util import dumpPorts
from mininet.term import makeTerms


class MyTopo(Topo):
    def __init__(self, nhosts):
        
        self.nhosts = nhosts
        #self.build()
        Topo.__init__(self)

    def build(self):
        s1 = self.addSwitch('s1')
        if self.nhosts == 2:
            self.addHost('JuanLopez')
            self.addHost('Hamelin')
            self.addLink('JuanLopez', s1)
            self.addLink('Hamelin', s1, loss=10)
        return
        # else:
            # server = self.addHost('server')
            # hosts = ['h' + str(i) for i in range(1, self.nhosts + 1)]
            # for host in hosts:
            #     self.addHost(host)
            #     self.addLink(server, s1)

        # cada host se conecta con el server a traves de un solo switch
        # todo link tiene una perdida de 5% tal que una conexion host-server tiene una perdida de 10%
        # for h in self.hosts():
        #     self.addLink(h, s1, loss=5, bw = 100) 

if __name__ == '__main__':
        
    parser = argparse.ArgumentParser()
    parser.add_argument('--nhosts', '-n', type=int, default=2)
    args = parser.parse_args()
    topo = MyTopo(args.nhosts)
    net = Mininet(topo=topo, link=TCLink, controller=Controller)

    net.start()
    dumpPorts(net.hosts)
    makeTerms(net.hosts)
#     for host in net.hosts:
#          makeTerm(host) 

    CLI(net)