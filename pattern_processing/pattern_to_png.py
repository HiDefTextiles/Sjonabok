# pattern_to_png.py

import cv2
import numpy as np
from .utils import read_txt_to_matrix

COLOR_PALETTE = [
    (16, 9, 159),  # HI-Blue
    (214, 31, 105),  # HI-Pink
    (244, 184, 206),  # HI-Pink-Light
    (45, 210, 192)  # HI-Green
]


def apply_color_palette(matrix, palette):
    """
    Applies a color palette to a binary matrix.

    :param matrix: Binary matrix (numpy array)
    :param palette: List of RGB tuples representing the color palette
    :return: Colored image matrix
    """
    h, w = matrix.shape
    color_image = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(1, len(palette) + 1):
        color_image[matrix == i] = palette[i - 1]

    return color_image


def convert_txt_to_png(input_txt, output_png):
    """
    Converts a TXT file containing a binary matrix to a PNG image using a color palette.

    :param input_txt: Path to the input TXT file
    :param output_png: Path to the output PNG file
    :return: Saves the PNG file at the specified path
    """
    matrix = read_txt_to_matrix(input_txt)

    # Apply color palette
    colored_image = apply_color_palette(matrix, COLOR_PALETTE)

    # Save the image as PNG
    cv2.imwrite(output_png, colored_image)
