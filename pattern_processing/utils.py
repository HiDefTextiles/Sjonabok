# utils.py

import numpy as np


def read_txt_to_matrix(txt_file):
    """
    Reads a TXT file and converts it to a binary matrix.

    :param txt_file: Path to the TXT file
    :return: Binary matrix (numpy array)
    """
    with open(txt_file, 'r') as file:
        lines = file.read().splitlines()
        data = [list(line) for line in lines]
        matrix = np.array(data, dtype=int)

    return matrix
