# utils.py

import numpy as np
import re


def read_txt_to_matrix(txt_file):
    """
    Reads a TXT file and converts it to a binary matrix.

    :param txt_file: Path to the TXT file
    :return: Binary matrix (numpy array)
    """
    with open(txt_file, 'r', encoding='utf-8') as file:
        lines = [line.strip() for line in file if line.strip()]
    data = []
    for line in lines:
        if re.search(r'[\s,]', line):
            data.append([int(value) for value in re.split(r'[\s,]+', line) if value])
        else:
            data.append([int(value) for value in line])
    if len({len(row) for row in data}) > 1:
        raise ValueError(f'Rows in {txt_file} have different cell counts')
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
