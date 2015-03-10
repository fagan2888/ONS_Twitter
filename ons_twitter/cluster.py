"""
Description:    Code for the DBScan clustering algorithm.
Author:         Bence Komarniczky
Date:           09/03/2015
Python version: 3.4
"""

import numpy as np


def create_dictionary_for_chunk(mongo_client, chunk_id):
    """
    Takes a mongo_db connection and a chunk_id as from the twitted mongodb database. Returns a dictionary,
    where each key is a user_id and each value is the list of all tweets from that user.

    :param mongo_client:    Active mongodb connection to twitter database
    :param chunk_id:        Number of chunk to process. 0-999
    :return:                Dictionary with user_id: [tweets]
    """

    # set up query
    query = {"chunk_id": chunk_id}

    # collect cursor
    cursor = mongo_client.find(query, {"_id": 1, "user_id": 1, "tweet.coordinates": 1})

    # initiate dictionary
    tweets_by_user = {}
    for new_tweet_mongo in cursor:
        new_tweet = [new_tweet_mongo["_id"],
                     new_tweet_mongo["user_id"],
                     new_tweet_mongo["tweet"]["coordinates"]]

        # insert into dictionary
        try:
            tweets_by_user[new_tweet_mongo["user_id"]].append(new_tweet)
        except KeyError:
            tweets_by_user[new_tweet_mongo["user_id"]] = [new_tweet]

    return tweets_by_user


def euclidean_distances_matrix(vector1, vector2):
    """
    Takes two complex vectors and returns a euclidean distance matrix.
    Input should be A[j] = x[j] + i*y[j]

    :param vector1: Complex numpy vector
    :param vector2: Complex numpy vector
    :return:        Euclidean distance matrix
    """

    # get two matrices with all possible point combinations
    m, n = np.meshgrid(vector1, vector2)

    # take the difference of their absolute values, this is the euclidean distance by definition
    distance_array = abs(m - n)

    # convert them into integers
    distance_array_integer = distance_array.astype('int32')

    return distance_array_integer


def distance_matrix(point_list, block_size=1000):
    """
    For a given list of input points (Tweets) returns the distance matrix. Uses numpy arrays and complex numbers.
    In order to fit into memory, there is a block_size parameter that breaks up the computation into chunks.
    With block_size= 1000, it can process 21,000 tweets within 22 seconds, using approximately 7Gb ram.

    :param point_list: _id, user_id, coordinates tuples
    :param block_size: break point for chunks, tweets over this size will be processed in chunks.
    :return:    numpy array of distance matrix
    """

    # create numpy array from input points
    all_points = np.array([complex(one_tweet[2][0], one_tweet[2][1]) for one_tweet in point_list])

    # count the size of input
    n = len(point_list)

    # do blocks/don't do blocks
    if n < block_size:

        # simply calculate distance
        distance_array_integer = euclidean_distances_matrix(all_points, all_points)

    else:
        # initiate empty matrix
        distance_array_integer = np.empty((n, n), dtype="int32")

        # calculate the number of required blocks
        blocks = n // block_size

        # iterate over block ids
        for row_id in range(blocks + 1):
            # attach new strip to matrix
            distance_array_integer[:, (row_id * block_size):((row_id + 1) * block_size)] =\
                euclidean_distances_matrix(all_points[(row_id * block_size):((row_id + 1) * block_size)],
                                           all_points)

    return distance_array_integer


def create_one_cluster(cluster_points, remaining_mask, distance_array, eps=20):
    """
    Create one new cluster for the user and return the remaining points.

    :param cluster_points:  list of cluster points, as supplied to the distance_matrix function
    :param remaining_mask:  list of a list and a numpy array. First list indicates the available row positions,
                            that have not been searched before. An updated version of this will be returned.
    :param distance_array:  numpy integer array of approximated euclidean distances, output of distance matrix
                            function.
    :param eps:             distance parameter for dbscan algorithm
    :return: new_cluster:   list of all points from cluster_points, belonging to the new cluster
    :return: remaining_mask:updated remaining mask, None if user's tweets have been exhausted
    """

    # check if any mask remains
    if len(remaining_mask[1]) == 0:
        return None, remaining_mask

    # pick first element, start populating new_cluster
    search_row = remaining_mask[0].pop(0)
    new_cluster = [cluster_points[search_row]]

    # delete first column
    remaining_mask[1] = np.delete(remaining_mask[1], 0)

    # search for that one row
    found = remaining_mask[1][distance_array[search_row, remaining_mask[1]] < eps]

    # find all other rows that are close to row 1
    search_these = []
    for found_index in found:
        # add point to cluster and remove column from distance array
        new_cluster.append(cluster_points[found_index])
        remaining_mask[1] = np.delete(remaining_mask[1], np.where(remaining_mask[1] == found_index))
        search_these.append(found_index)

    # duplicate search list for looping
    new_search_list = search_these[:]

    # do this until cluster cannot grow any more
    while len(new_search_list) > 0:
        # loop through all found indices
        for search_row in search_these:

            # remove searched row from mask
            remaining_mask[0].remove(search_row)

            # search row
            found = remaining_mask[1][distance_array[search_row, remaining_mask[1]] < eps]

            # search all found indices
            for found_index in found:
                # add point to cluster and remove column from distance array
                new_cluster.append(cluster_points[found_index])
                remaining_mask[1] = np.delete(remaining_mask[1], np.where(remaining_mask[1] == found_index))
                search_these.append(found_index)

            # remove search row if hasn't been removed yet
            try:
                new_search_list.remove(search_row)
            except ValueError:
                # skip if value has already been deleted
                continue

        # update search_these list for while statement
        search_these = new_search_list[:]

    return new_cluster, remaining_mask


# def create_cluster_info(complete_cluster, cluster_name):
#     """
#     Returns more information for the cluster. Mean of distances, maximum distance, standard deviation of distances
#     from cluster centroid.
#
#     :param complete_cluster: list of all points in completed cluster
#     :return:    json formatted dictionary for mongodb insert
#     """
#
#     coordinate_points =