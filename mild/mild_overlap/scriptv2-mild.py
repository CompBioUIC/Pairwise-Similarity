import networkx as nx
import numpy as np
import os
import json
import math
import sys
from scipy.stats import expon
from tqdm import tqdm

# given a number of ele, n, this function extracts first n ele and returns the remaining array.


def extract_ele(arr, idx):
    del_el = arr[:idx]
    return np.array(del_el), np.delete(arr, range(idx))


def sizes_of_dist(N):
    n_sizes = np.array([])
    remain = N
    while remain > 1:
        X = math.floor(remain/1.1)
        n_sizes = np.append(n_sizes, X)
        remain = remain - X
    if remain:
        n_sizes[-1] += remain
    return n_sizes, n_sizes.size


def gen_similarity_scores_not_same(sizes, chunks):
    sim_scores = np.array([])
    chunk = 1/chunks
    ranges = np.arange(0, 1, chunk)
    for i in range(chunks):
        z = np.zeros(int(sizes[i])) + np.around(ranges[i] + chunk, 2)
        # print(ranges[i], ranges[i] + chunk, sizes[i])
        sim_scores = np.append(sim_scores, z)
    sim_scores = sim_scores + chunk
    sim_scores[-1] -= chunk
    np.random.shuffle(sim_scores)
    return sim_scores


def gen_similarity_scores_same(sizes, chunks):
    sim_scores = np.array([])
    chunk = 1/chunks
    ranges = 1 - np.arange(0, 1, chunk)
    for i in range(chunks):
        # print(ranges[i], np.abs(np.around(ranges[i] - chunk, 2)), sizes[i])
        z = np.zeros(int(sizes[i])) + np.abs(np.around(ranges[i] - chunk, 2))
        sim_scores = np.append(sim_scores, z)
    sim_scores = sim_scores - chunk
    sim_scores[-1] += chunk
    return sim_scores


'''The following function creates the clusters that are essentially complete graphs.'''


def make_clusters(cluster_sizes):
    graph_list = []
    counter = 0
    for size in cluster_sizes:
        g = nx.complete_graph(size)
        g = nx.convert_node_labels_to_integers(g, first_label=counter+1)
        graph_list.append(g)
        counter += size
    return graph_list


'''Generate cluster sizes for clusters according to size parameters.'''


def cluster_sizing(total_number_data, number_of_clusters, x):
    # store the cluster sizes in an array.
    array = np.ones((number_of_clusters,), dtype=int)
    remain = total_number_data - number_of_clusters
    for i in range(array.size):
        if remain < 1:
            break
        fraction = int(x * remain)
        array[i] += fraction
        remain -= fraction
    # deal with remaining values after end of loops.
    if remain:
        array[0] += remain

    return array


'''Create the ground truth for 'SAME', ie, the clusters themselves. They are the SAME components of the graph.'''


def ground_truth_same(cluster_size_array):
    # store all the nodes for future use to create global graph.
    node_list = []
    # store all edges for future use as above.
    edge_list = []
    # list of clusters generated by said function.
    cluster_list = make_clusters(cluster_size_array)
    count = 1
    # store the number of pairs in the 'SAME' distribution.
    pairs_SAME = 0
    for c in cluster_list:
        # node_label = ', '.join(str(e) for e in c.nodes)
        node_list.append(list(c.nodes))
        edge_list.append(list(c.edges))
        count += 1
        pairs_SAME += c.number_of_edges()

    # flatten list of lists into single list.
    node_list = [item for sublist in node_list for item in sublist]
    edge_list = [item for sublist in edge_list for item in sublist]
    print(f'''Number of pairs in 'SAME' distribution: {pairs_SAME}''')

    return node_list, cluster_list, edge_list, pairs_SAME


'''Create the ground truth for 'NOT SAME', ie, the global graph minus the edges present in 'SAME' clusters.'''


def ground_truth_not_same(edge_list, node_list):
    # create a global graph of nodes = sum of all nodes in all clusters.
    global_graph = nx.complete_graph(node_list)
    # remove all edges that are 'SAME'
    global_graph.remove_edges_from(edge_list)
    # hold on to the number of 'NOT SAME' pairs/edges to sample from exponential distribution.
    pair_NOT_SAME = global_graph.number_of_edges()
    print(f'''Number of pairs in 'NOT_SAME' distribution: {pair_NOT_SAME}''')

    return global_graph, pair_NOT_SAME


'''Assign 'SAME' similarity score to edges within the clusters'''


def assign_same(cluster_list, pairs_SAME):
    sizes, chunks = sizes_of_dist(pairs_SAME)
    sim_scores = gen_similarity_scores_same(sizes, chunks)
    for cluster in cluster_list:
        edge_count = cluster.number_of_edges()
        similarity_scores, sim_scores = extract_ele(sim_scores, edge_count)
        keys = [e for e in cluster.edges]
        values = 1 - similarity_scores
        # assign the similarity scores to the edges within cluster.
        new_dict = {k: v for k, v in zip(keys, values)}
        nx.set_edge_attributes(cluster, new_dict, name='sim_score')

    return cluster_list


'''Assign 'NOT SAME' similarity score to edges in the modified global graph.'''


def assign_not_same(global_graph, pair_NOT_SAME):
    sizes, chunks = sizes_of_dist(pair_NOT_SAME)
    similarity_scores = gen_similarity_scores_not_same(sizes, chunks)
    keys = [e for e in global_graph.edges]
    new_dict = {k: v for k, v in zip(keys, similarity_scores)}
    nx.set_edge_attributes(global_graph, new_dict, name='sim_score')

    return global_graph


'''Collect data for generating histograms from SAME and NOT SAME samples.'''


def collect_hist_data(cluster_list, global_graph):
    # collect similarity scores of 'SAME' and 'NOT SAME' into arrays.
    same = []
    for cluster in cluster_list:
        this_list = list(nx.get_edge_attributes(cluster, 'sim_score').values())
        same.append(this_list)

    not_same = list(nx.get_edge_attributes(global_graph, 'sim_score').values())
    # flattening list of lists into single list, ie, numpy array.
    SAME = np.array([score for score_list in same for score in score_list])
    NOT_SAME = np.array(not_same)

    return SAME, NOT_SAME


'''Calculate the confusion matrix (theoretical bounds) for 'same' and 'not same' distribution.'''


def flip_intercluster(global_graph, same_threshold, not_same_threshold):
    dont_care_edges = []
    false_negatives = []
    # iterate over the intercluster edges and flip the labels.
    for edge in list(global_graph.edges):
        the_edge = global_graph.edges[edge]
        the_edge['original_location'] = 'intercluster'
        sim_score = the_edge['sim_score']
        if sim_score >= same_threshold:
            the_edge['flipped'] = True
            false_negatives.append(edge)
            continue
        if sim_score > not_same_threshold and sim_score < same_threshold:
            dont_care_edges.append(edge)
            the_edge['dont_care'] = True
    global_graph.graph['dont_care'] = dont_care_edges
    global_graph.graph['false_negatives'] = false_negatives
    return global_graph


def flip_intracluster(cluster_list, same_threshold, not_same_threshold):
    for cluster in cluster_list:
        dce_list = []
        # iterate over the edges of the cluster and flip labels.
        for edge in list(cluster.edges):
            the_edge = cluster.edges[edge]
            the_edge['original_location'] = 'intracluster'
            sim_score = the_edge['sim_score']
            if sim_score <= not_same_threshold:
                the_edge['flipped'] = True
                continue
            if sim_score > not_same_threshold and sim_score < same_threshold:
                dce_list.append(edge)
                the_edge['dont_care'] = True
        cluster.graph['dont_care'] = dce_list
    return cluster_list


def confusion_matrix_ground_truth(global_graph, cluster_list):
    # flipped edges intercluster are FN and flipped edges intracluster are FP.
    TP = 0
    TN = 0
    FP = 0
    FN = 0
    for edge in list(global_graph.edges):
        try:
            if global_graph.edges[edge]['flipped']:
                FN += 1
        except:
            try:
                if global_graph.edges[edge]['dont_care']:
                    pass
            except:
                TN += 1

    for cluster in cluster_list:
        for edge in list(cluster.edges):
            try:
                if cluster.edges[edge]['flipped']:
                    FP += 1
            except:
                try:
                    if cluster.edges[edge]['dont_care']:
                        pass
                except:
                    TP += 1

    try:
        precision = TP / (TP + FP)
    except:
        precision = 0

    try:
        recall = TP / (TP + FN)
    except:
        recall = 0

    try:
        f_score = 2*precision*recall / (precision + recall)
    except:
        f_score = 0

    return TP, TN, FP, FN, "{0:f}".format(precision), "{0:f}".format(recall), "{0:f}".format(f_score)


def flipped_true(edge, graph):
    try:
        if graph.edges[edge]['flipped']:
            return True
    except:
        return False


def dont_care_true(edge, graph):
    try:
        if graph.edges[edge]['dont_care']:
            return True
    except:
        return False


def make_new_graph(global_graph, cluster_list):

    # collect attributes that will be needed.
    attr_dict2 = nx.get_edge_attributes(global_graph, 'original_location')

    # collect all false negative edges which will not be added to new 2cc graph.
    new_graph = nx.Graph()
    new_graph.add_nodes_from(global_graph.nodes)
    new_graph.add_edges_from(global_graph.graph['false_negatives'])
    nx.set_edge_attributes(
        new_graph, name='original_location', values=attr_dict2)

    # drop DONT CARE edges in each cluster, add remaining edges to the graph.
    for cluster in cluster_list:
        # collect attributes that will be needed.
        attr_dict2 = nx.get_edge_attributes(cluster, 'original_location')

        new_graph.add_edges_from(cluster.edges)
        new_graph.remove_edges_from(cluster.graph['dont_care'])
        nx.set_edge_attributes(
            new_graph, name='original_location', values=attr_dict2)

    return new_graph


def biconnected_components_gen(new_graph):
    return [edge for list in nx.biconnected_component_edges(new_graph) for edge in list]


def remove_bcc_edges_from_new_graph(new_graph, bcc_edges_list):
    bcc_edges_graph = nx.Graph()
    bcc_edges_graph.add_nodes_from(list(new_graph.nodes))
    bcc_edges_graph.add_edges_from(bcc_edges_list)
    # find the edges that are present in new graph but not in any bcc's.
    edge_list = list(nx.difference(new_graph, bcc_edges_graph).edges)
    return edge_list


def bcc_accuracy(bcc_edges_list, new_graph):
    TP = 0
    FP = 0
    TN = 0
    FN = 0

    for edge in bcc_edges_list:
        the_edge = new_graph.edges[edge]
        if the_edge['original_location'] == 'intercluster':
            FP += 1
        else:
            TP += 1

    new_graph_edges_non_bcc = remove_bcc_edges_from_new_graph(
        new_graph, bcc_edges_list)

    for edge in new_graph_edges_non_bcc:
        the_edge = new_graph.edges[edge]
        if the_edge['original_location'] == 'intracluster':
            FN += 1
        else:
            TN += 1

    precision = TP / (TP + FP)
    recall = TP / (TP + FN)
    f_score = 2*precision*recall / (precision + recall)

    return TN, FN, TP, FP, "{0:f}".format(precision), "{0:f}".format(recall), "{0:f}".format(f_score)


def perform_all_steps_10_times(number_of_clusters, nodes_multiplier, cluster_list, global_graph, pairs_SAME, pair_NOT_SAME, threshold):

    score_dict = {}
    score_dict['ground'] = {'p': [], 'r': [], 'f': []}
    score_dict['bcc'] = {'p': [], 'r': [], 'f': []}

    for iteration in tqdm(range(5)):

        print('iteration # ' + str(iteration + 1))

        # assign similarity scores to the 'SAME' pairs in the clusters.
        cluster_list = assign_same(cluster_list, pairs_SAME)

        # assign similarity scores to the 'NOT SAME' pairs in the clusters.
        global_graph = assign_not_same(global_graph, pair_NOT_SAME)

        # collect the sampled data from the ground truth for generation of histogram.
        SAME, NOT_SAME = collect_hist_data(cluster_list, global_graph)

        same_threshold = np.percentile(SAME, threshold)
        print(f'same threshold: {same_threshold}')

        not_same_threshold = np.percentile(NOT_SAME, 100-threshold)
        print(f'not-same_threshold: {not_same_threshold}')

        # pick values of x & y which are the thresholds for SAME/NOT SAME. These values reflect similarity scores [0,1]
        x = not_same_threshold
        y = same_threshold

        # find the False Positives and False Negatives and get them ready for flipping.
        cluster_list = flip_intracluster(
            cluster_list, same_threshold, not_same_threshold)
        global_graph = flip_intercluster(
            global_graph, same_threshold, not_same_threshold)

        # calculate accuracy of classification, after applying same/not same thresholds on ground truth.
        TP, TN, FP, FN, precision, recall, f_score = confusion_matrix_ground_truth(
            global_graph, cluster_list)
        print(f'''TN = {TN}, FP = {FP}, TP = {TP}, FN = {FN}''')
        print(
            f'''Precision = {precision}, Recall = {recall}, F1-Score = {f_score}''')
        score_dict['ground']['p'].append(precision)
        score_dict['ground']['r'].append(recall)
        score_dict['ground']['f'].append(f_score)

        # Generate new graph to find biconnected components.
        new_graph = make_new_graph(global_graph, cluster_list)

        # collect all the edges as part of all biconnected components.
        biconnected_components_edgelist = biconnected_components_gen(new_graph)

        # calculate accuracy of biconnected component clusters.
        TN, FN, TP, FP, precision, recall, f_score = bcc_accuracy(
            biconnected_components_edgelist, new_graph)
        print(f'''FP = {FP}, TP = {TP}, FN = {FN}, TN = {TN}''')
        print(
            f'''Precision = {precision}, Recall = {recall}, F1-score = {f_score}''')
        score_dict['bcc']['p'].append(precision)
        score_dict['bcc']['r'].append(recall)
        score_dict['bcc']['f'].append(f_score)

    title = 'output: ' + 'n: ' + str(number_of_clusters) + ' ' + 'm: ' + str(
        nodes_multiplier) + ' ' + 's: ' + ' ' + 'ns: ' + ' ' + 't: ' + str(threshold) + '.txt'

    destination = os.path.join(os.getcwd(), 'mild')

    f = open(os.path.join(destination, title), 'w')

    json.dump(score_dict, f)
    f.close()


def main():
    # cluster_params = [(200, 3), (200, 5), (200, 10), (500, 3), (500, 5), (500, 10), (1000, 3), (1000, 5)]

    cluster_params = [(5000, 3), (5000, 5)]

    for number_of_clusters, nodes_multiplier in cluster_params:
        print('=======================================')
        print(
            f'''Number of clusters = {number_of_clusters}, multiplier = {nodes_multiplier}''')

        # create cluster sizes.
        clusters = cluster_sizing(total_number_data=number_of_clusters *
                                  nodes_multiplier, number_of_clusters=number_of_clusters, x=0.5)

        # create the ground truth for 'SAME'.
        node_list, cluster_list, edge_list, pairs_SAME = ground_truth_same(
            clusters)

        print(sys.getsizeof(cluster_list))

        # create the ground truth for 'NOT SAME'
        global_graph, pair_NOT_SAME = ground_truth_not_same(
            edge_list, node_list)

        for threshold in [98, 50]:
            print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
            print(
                f'''Current Number of clusters = {number_of_clusters}, multiplier = {nodes_multiplier}''')
            print(f'''threshold = {threshold}''')
            perform_all_steps_10_times(number_of_clusters, nodes_multiplier, cluster_list,
                                       global_graph, pairs_SAME, pair_NOT_SAME, threshold)


if __name__ == "__main__":
    main()
