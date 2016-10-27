from __future__ import division

from structural_variant.constants import *
from structural_variant.interval import Interval
from structural_variant.breakpoint import BreakpointPair, Breakpoint

import itertools
import networkx as nx
import warnings


class IntervalPair:
    def __init__(self, start, end, id=None):
        self.id = id
        self.start = start if isinstance(start, Interval) else Interval(start[0], start[1])
        self.end = end if isinstance(end, Interval) else Interval(end[0], end[1])
    
    def __eq__(self, other):
        if not hasattr(other, 'start') or not hasattr(other, 'end') or not hasattr(other, 'id') \
                or self.start != other.start or self.end != other.end or self.id != other.id:
            return False
        return True

    def __lt__(self, other):
        if self.start < other.start:
            return True
        elif self.start == other.start and self.end < other.end:
            return True
        return False

    def __hash__(self):
        return hash((self.start, self.end, self.id))

    @classmethod
    def weighted_mean(cls, interval_pairs):
        start = Interval.weighted_mean([i.start for i in interval_pairs])
        end = Interval.weighted_mean([i.end for i in interval_pairs])
        return IntervalPair(start, end)

    def dist(self, other):
        d = abs(self.start.center - other.start.center)
        d += abs(self.end.center - other.end.center)
        d /= 2
        return d

    def __repr__(self):
        return '{}<{}, {}, id={}>'.format(self.__class__.__name__, self.start, self.end, self.id)

    @classmethod
    def _redundant_maximal_kcliques(cls, G, k=10):
        """
        for a give graph returns all cliques up to a size k
        any clique which is a proper subset of another clique is removed
        nodes can participate in multiple cliques if they are equal fit
        """
        if k < 1:
            raise AttributeError('k must be greater than 0')
        if k >= 20:
            warnings.warn('k >= 20 is not recommended as the number of combinations increases exponentially')

        cliques = []
        for component in nx.connected_components(G):
            comp_cliques = []
            # take an exhaustive approach to finding the possible cliques
            for ktemp in range(1, k + 1):
                for putative_kclique in itertools.combinations(component, ktemp):
                    if is_complete(G, putative_kclique):
                        cliques.append(set(putative_kclique))

        # remove subsets to ensure cliques are maximal (up to k)
        refined_cliques = []
        for i in range(0, len(cliques)):
            is_subset = False
            for j in range(i + 1, len(cliques)):
                if cliques[i].issubset(cliques[j]):
                    is_subset = True
                    break
            if not is_subset:
                refined_cliques.append(cliques[i])

        participation = {}
        for c in refined_cliques:
            for node in c:
                participation[node] = participation.get(node, 0) + 1

        for count, node in sorted([(c, n) for n, c in participation.items() if c > 1], reverse=True):
            distances = []
            for cluster in refined_cliques:
                if node not in cluster:
                    continue
                d = sum([node.dist(x) for x in cluster if x != node]) / (len(cluster) - 1)
                distances.append((d, cluster))
            lowest = min(distances, key=lambda x: x[0])[0]
            for score, cluster in distances:
                if score > lowest:
                    cluster.remove(node)

        for node in G.nodes():
            found = False
            for clique in refined_cliques:
                if node in clique:
                    found = True
                    break
            if not found:
                raise AssertionError(
                    'error, lost a node somehow', node, refined_cliques)
        return refined_cliques
    
    @classmethod
    def _redundant_ordered_hierarchical_clustering(cls, groups, r):
        queue = sorted(groups, key=lambda x: IntervalPair.weighted_mean(x))
        complete_groups = []

        while len(queue) > 0:
            temp_queue = []
            for i in range(0, len(queue)):
                merged = False
                curr = queue[i]
                curri = IntervalPair.weighted_mean(curr)
                if i > 0:
                    prev = queue[i - 1]
                    if IntervalPair.weighted_mean(prev).dist(curri) <= r:
                        d = curr | prev
                        if d not in temp_queue:
                            temp_queue.append(d)
                        merged = True
                if i < len(queue) - 1:
                    nexxt = queue[i + 1]
                    if IntervalPair.weighted_mean(nexxt).dist(curri) <= r:
                        d = curr | nexxt
                        if d not in temp_queue:
                            temp_queue.append(d)
                        merged = True
                if not merged:
                    complete_groups.append(curr)
            queue = sorted(temp_queue, key=lambda x: IntervalPair.weighted_mean(x))
        return complete_groups

    @classmethod
    def cluster(cls, pairs, r, k):
        # build the initial graph
        G = nx.Graph()
        for curr, other in itertools.combinations(pairs, 2):
            if curr.dist(other) <= r:
                G.add_edge(curr, other)
        
        # pull out the highly connected components
        subgraphs = cls._redundant_maximal_kcliques(G, k)
        subgraphs = cls._redundant_ordered_hierarchical_clustering(subgraphs, r)
        return subgraphs


def is_complete(G, N):
    """
    for a given input graph and a set of nodes N in G
    checks if N is a complete subgraph of G
    """
    for node, other in itertools.combinations(N, 2):
        if not G.has_node(node) or not G.has_node(other):
            raise AttributeError('invalid node is not part of the input graph')
        if not G.has_edge(node, other):
            return False
    return True


def cluster_breakpoint_pairs(input_pairs, r, k):
    # 0. sort the breakpoints by start and then end
    # 1a. split/duplicate breakpoints into sets of things that could possibly support the same event
    # 1b. split breakpoint pairs by chr pair (can be the same chr)
    # 2. set the initial clusters based on overlap
    # 3. iterate over the clusters
    #   # stop when no clusters improve/change or we hit a maximum number of iterations
    # classify the breakpoints.... by the possible pairs they could support
    # (explicit only)

    node_sets = {}
    
    for index, bpp in enumerate(input_pairs):

        for chr1, chr2, o1, o2, s1, s2 in itertools.product(
                [bpp.break1.chr],
                [bpp.break2.chr],
                ORIENT.expand(bpp.break1.orient),
                ORIENT.expand(bpp.break2.orient),
                [bpp.break1.strand],
                [bpp.break2.strand]
        ):
            if bpp.opposing_strands != (s1 != s2) and s1 != STRAND.NS and s2 != STRAND.NS:
                continue
            b1 = Interval(bpp.break1.start, bpp.break1.end)
            b2 = Interval(bpp.break2.start, bpp.break2.end)
            new_bpp = IntervalPair(b1, b2, index)
            
            classification_key = chr1, chr2, o1, o2, s1, s2, bpp.opposing_strands
            node_sets.setdefault(classification_key, []).append(new_bpp)
    
    result = {}
    for key, group in node_sets.items():
        chr1, chr2, o1, o2, s1, s2, opposing_strands = key
        clusters = IntervalPair.cluster(group, r, k)
        for node in group:
            particpation = sum([ 1 for c in clusters if node in c])
            if particpation > 1:
                warnings.warn('interval pair participates in multiple clusters')
        for c in clusters:
            ip = IntervalPair.weighted_mean(c)
            b1 = Breakpoint(chr1, ip.start[0], ip.start[1], strand=s1, orient=o1)
            b2 = Breakpoint(chr2, ip.end[0], ip.end[2], strand=s2, orient=o2)
            bpp = BreakpointPair(b1, b2, opposing_strands=opposing_strands)
            inputs = [input_pairs[k.id] for k in c] 
            result.setdefault(bpp, set()).update(set(inputs))
    return result

