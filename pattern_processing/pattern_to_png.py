from PIL import Image
import numpy as np
from .utils import read_txt_to_matrix

COLOR_PALETTE = [
    (0, 0, 0, 0),  # Transparent (RGBA) for 0
    (16, 9, 159, 255),  # HI-Blue for 1
    (214, 31, 105, 255),  # HI-Pink for 2
    (244, 184, 206, 255),  # HI-Light Pink for 3
    (45, 210, 192, 255)  # HI-Green for 4
]


def apply_color_palette(matrix, palette):
    """
    Applies a color palette with transparency to a binary matrix.

    :param matrix: Binary matrix (numpy array)
    :param palette: List of RGBA tuples representing the color palette
    :return: Colored image matrix with an alpha channel for transparency
    """
    h, w = matrix.shape
    color_image = np.zeros((h, w, 4), dtype=np.uint8)  # Note the 4 channels (RGBA)

    for i in range(len(palette)):
        color_image[matrix == i] = palette[i]

    # Have a warning if there is a color in the matrix that is not in the palette
    assert len(np.unique(matrix)) <= len(
        palette), "There are more colors in the matrix than in the palette."

    return color_image


def convert_txt_to_png(input_txt, output_png):
    """
    Converts a TXT file containing a binary matrix to a PNG image with transparency.

    :param input_txt: Path to the input TXT file
    :param output_png: Path to the output PNG file
    :return: Saves the PNG file at the specified path
    """
    matrix = read_txt_to_matrix(input_txt)

    # Apply color palette
    colored_image = apply_color_palette(matrix, COLOR_PALETTE)

    # Convert the image array to a Pillow Image object
    image = Image.fromarray(colored_image, mode='RGBA')

    # Save the image as PNG with transparency
    image.save(output_png)
