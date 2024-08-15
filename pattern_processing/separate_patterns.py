import numpy as np
from .utils import read_txt_to_matrix

def split_patterns(input_txt, distance_between_rows, distance_between_columns):
    """
    Splits a pattern into sub-patterns based on the distance between rows and columns.
    :param input_txt: Filepath to the input TXT file
    :param distance_between_rows: The distance between rows in the pattern for separation
    :param distance_between_columns: The distance between columns in the pattern for separation
    :return: Number of sub-patterns created
    """

    matrix = read_txt_to_matrix(input_txt)

    row_patterns = separate_patterns_simple(matrix, axis=0,
                                            DISTANCE_BETWEEN_PATTERNS=distance_between_rows)
    sub_patterns = []
    for row_pattern in row_patterns:
        col_pattern = separate_patterns_simple(row_pattern, axis=1,
                                               DISTANCE_BETWEEN_PATTERNS=distance_between_columns)
        sub_patterns.extend(col_pattern)

    if len(sub_patterns) > 1:
        for idx, pattern in enumerate(sub_patterns):
            output_path = input_txt.replace('.txt', f'_p{idx + 1}.txt')
            np.savetxt(output_path, pattern, fmt='%d', delimiter='')
        print(f"Pattern separated into {len(sub_patterns)} sub-patterns.")

    return len(sub_patterns)

def remove_boarder_of_pattern(matrix):
    '''
    Use: new_matrix = remove_boarder_of_pattern(matrix)
    Pre: matrix is a binary matrix of a pattern from Sjonabok. 
    Post: If any empty rows or columns are outside of the pattern, they are removed. 
    '''
    n, m = matrix.shape
    ls, rs, t, b = 0, m - 1, 0, n - 1  # initiate variables: leftside, rightside, top, bottom

    # left side
    while ls <= rs and np.sum(matrix[:, ls]) == 0:
        ls += 1

    # right side
    while rs >= ls and np.sum(matrix[:, rs]) == 0:
        rs -= 1

    # top
    while t <= b and np.sum(matrix[t, :]) == 0:
        t += 1

    # bottom
    while b >= t and np.sum(matrix[b, :]) == 0:
        b -= 1

    matrix = matrix[t:b + 1, ls:rs + 1]
    return matrix


def separate_patterns_simple(matrix, axis=0, DISTANCE_BETWEEN_PATTERNS=5):
    '''
    Usage: pattern_idx = separate_patterns_simple(matrix)
    Pre:   matrix is a binary matrix of a pattern from Sjonabok, axis is by which axis the separation
           of patterns is searched for. If 0 then row wise, if 1 then column wise
    Post:  If matrix has more than 1 individual patterns separated entirely either by whole rows/columns 
           then pattern_idx is a list of tuples where each tuple contains the beginning and end of each pattern.
           If patterns in matrix are separated in more complex ways use the find_separation_of_patterns_complex 
           function instead. If no individual patterns found the function returns the original
           matrix as a list.
    '''
    if axis == 1:
        matrix = matrix.T

    n = len(matrix)

    patterns = []

    last_encountered_cross_row = 0
    beginning_of_pattern_row = 0
    for i in range(n):
        if beginning_of_pattern_row > last_encountered_cross_row:
            if np.sum(matrix[i, :]):
                beginning_of_pattern_row = i
                last_encountered_cross_row = i
        else:
            if np.sum(matrix[i, :]):
                last_encountered_cross_row = i
            if i - last_encountered_cross_row == DISTANCE_BETWEEN_PATTERNS:
                patterns.append(remove_boarder_of_pattern(
                    matrix[beginning_of_pattern_row:last_encountered_cross_row + 1,
                    :]))  # (beginning_of_pattern_row,last_encountered_cross_row))
                beginning_of_pattern_row = i

    if patterns:  # if individual patterns found append the last pattern but discard empty cols/rows if any
        last_pattern = remove_boarder_of_pattern(matrix[beginning_of_pattern_row:, :])
        patterns.append(last_pattern)

        if axis == 1:  # transpose patterns before returning
            for i in range(len(patterns)):
                patterns[i] = patterns[i].T

    return patterns if patterns else [matrix if axis == 0 else matrix.T]


def find_first_one_in_array(array):
    '''
    Use: l = find_first_one_in_array(array):
    Pre: array is a binary list or an array
    Post: l is the first instance of 1 in the array
    '''
    for i in range(len(array)):
        if array[i]:
            return i
    raise ValueError("only zeros in array")


def separate_patterns_complex(matrix, patterns=[], DISTANCE_BETWEEN_PATTERNS=5):
    '''
    Use: individual_patterns = separate_patterns_complex(matrix,patterns=[],DISTANCE_BETWEEN_PATTERNS)
    Pre: matrix is a binary pattern matrix from Sjonabok, patterns is a list of an individual pattern matrices
          (connected components), DISTANCE_BETWEEN_PATTERNS is an integer > 0 and determines how far we look for
          a 1 in horizontal and vertical direction.
    Post: All connected components in matrix have been added to patterns i.e. patterns now contains all individual
          patterns from matrix. A 1 belongs to a connected component if it can be reached from either one step on 
          the diagonal or DISTANCE_BETWEEN_PATTERNS-1 in the vertical and horizontal directions. The patterns in the
          list patterns are ordered first by top to bottom and then from left to right.
    '''
    # If matrix is empty, return patterns
    if np.all(matrix == 0):
        return patterns

    pattern_found = 0
    while not pattern_found:
        if np.sum(matrix[0, :]):
            pattern_found = 1
        else:
            matrix = matrix[1:, :]  # discard empty rows
    n, m = matrix.shape

    tl = find_first_one_in_array(matrix[0, :])  # top left cross
    visited = []
    to_visit = [(0, tl)]
    while to_visit:
        current = to_visit[0]  # cross we are searching from
        to_visit = to_visit[1:]
        # search for 1 left, rigth, down and up 5 entries from current
        for i in range(1, DISTANCE_BETWEEN_PATTERNS):
            # searching up
            if (current[0] - i) >= 0:  # assuring we are not going out of matrix range
                searching_idx = (current[0] - i, current[1])
                if matrix[
                    searching_idx] and searching_idx not in visited and searching_idx not in to_visit:
                    to_visit.append(searching_idx)

            # searching down
            if (current[0] + i) < n:
                searching_idx = (current[0] + i, current[1])
                if matrix[
                    searching_idx] and searching_idx not in visited and searching_idx not in to_visit:
                    to_visit.append(searching_idx)

            # searching left
            if current[1] + i < m:
                searching_idx = (current[0], current[1] + i)
                if matrix[
                    searching_idx] and searching_idx not in visited and searching_idx not in to_visit:
                    to_visit.append(searching_idx)

            # searching right
            if current[1] - i >= 0:
                searching_idx = (current[0], current[1] - i)
                if matrix[
                    searching_idx] and searching_idx not in visited and searching_idx not in to_visit:
                    to_visit.append(searching_idx)

            # search for 1 diagonally 1 from current
            top_left_idx = (current[0] - 1, current[1] - 1)
            bottom_left_idx = (current[0] + 1, current[1] - 1)
            top_right_idx = (current[0] - 1, current[1] + 1)
            bottom_right_idx = (current[0] + 1, current[1] + 1)
            if top_left_idx[0] >= 0 and top_left_idx[1] >= 0 and matrix[
                top_left_idx] and top_left_idx not in visited and top_left_idx not in to_visit:
                to_visit.append(top_left_idx)

            if bottom_left_idx[0] < n and bottom_left_idx[1] >= 0 and matrix[
                bottom_left_idx] and bottom_left_idx not in visited and bottom_left_idx not in to_visit:
                to_visit.append(bottom_left_idx)

            if top_right_idx[0] >= 0 and top_right_idx[1] < m and matrix[
                top_right_idx] and top_right_idx not in visited and top_right_idx not in to_visit:
                to_visit.append(top_right_idx)

            if bottom_right_idx[0] < n and bottom_right_idx[1] < m and matrix[
                bottom_right_idx] and bottom_right_idx not in visited and bottom_right_idx not in to_visit:
                to_visit.append(bottom_right_idx)

            visited.append(current)  # mark as visited

    # Now that the connected component is found, remove pattern from matrix:
    for idx in visited:
        matrix[idx] = 0

    # find length and height of pattern
    c = [right for _, right in visited]  # column indexes
    r = [left for left, _ in visited]  # row indexes
    if min(c) != 0:  # scale elements if minimum value is not zero
        c = [el - min(c) for el in c]
    if min(r) != 0:
        r = [el - min(r) for el in r]

    # draw in the pattern
    pattern = np.zeros((max(r) + 1, max(c) + 1))
    for k in range(len(c)):
        pattern[r[k], c[k]] = 1

    patterns.append(pattern)  # keep pattern
    return separate_patterns_complex(matrix, patterns,
                                     DISTANCE_BETWEEN_PATTERNS)  # keep finding individual patterns until matrix is empty
