import argparse
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.util import dumpPorts
from mininet.term import makeTerms, cleanUpScreens


class MyTopo(Topo):
    def __init__(self, nhosts, arg_loss):

        self.nhosts = nhosts
        self.arg_loss = arg_loss
        Topo.__init__(self)

    def build(self):
        s1 = self.addSwitch("s1")
        if self.nhosts == 2:
            self.addHost('JuanLopez')
            self.addHost('Hamelin')
            self.addLink('JuanLopez', s1)
            self.addLink('Hamelin', s1, loss=self.arg_loss)
            return
        else:
            server = self.addHost('aserver')
            self.addLink(server, s1, loss=self.arg_loss)
            hosts = ['h' + str(i) for i in range(1, self.nhosts + 1)]

            for host in hosts:
                self.addHost(host)
                self.addLink(host, s1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nhosts", "-n", type=int, default=2)
    parser.add_argument("--loss", "-l", type=int, default=10)
    args = parser.parse_args()
    topo = MyTopo(args.nhosts, args.loss)
    net = Mininet(topo=topo, link=TCLink, controller=Controller)

    net.start()
    dumpPorts(net.hosts)
    makeTerms(net.hosts)
    CLI(net)
    cleanUpScreens()
    net.stop()
