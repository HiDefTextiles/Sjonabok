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

    height, width = get_matrix_size(matrix)
    print(f"Loaded pattern {txt_file} of size: {height}x{width} px")

    return matrix


def get_matrix_size(matrix):
    """
    Determines the size of the pattern matrix.

    :param matrix: Binary matrix (numpy array)
    :return: Tuple of the size (height, width) of the pattern matrix
    """
    return matrix.shape