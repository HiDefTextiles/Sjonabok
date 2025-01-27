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


def zoom_in(matrix, zoom_factor):
    """
    Zooms in a matrix by repeating pixels.
    """
    if zoom_factor == 1:
        return matrix
    elif zoom_factor < 1:
        raise ValueError("Zoom factor must be greater than or equal to 1.")
    else:
        return np.kron(matrix, np.ones((zoom_factor, zoom_factor), dtype=matrix.dtype))


def resize_with_crop_or_padding(matrix, target_width, target_height):
    """
    Resizes an integer matrix by cropping or padding to fit the target dimensions.

    :param matrix: Input 2D numpy array (the pattern matrix)
    :param target_width: Target width of the output matrix
    :param target_height: Target height of the output matrix
    :return: Resized matrix with the specified target dimensions
    """
    # Get the current dimensions of the matrix
    current_height, current_width = matrix.shape

    # Step 1: Crop if the matrix is larger than the target dimensions
    if current_width > target_width or current_height > target_height:
        # Calculate cropping bounds
        left = max((current_width - target_width) // 2, 0)
        top = max((current_height - target_height) // 2, 0)
        right = left + target_width
        bottom = top + target_height

        # Crop the matrix
        matrix = matrix[top:bottom, left:right]
        current_height, current_width = matrix.shape

    # Step 2: Pad if the matrix is smaller than the target dimensions
    if current_width < target_width or current_height < target_height:
        # Calculate padding amounts
        pad_top = max((target_height - current_height) // 2, 0)
        pad_left = max((target_width - current_width) // 2, 0)
        pad_bottom = target_height - current_height - pad_top
        pad_right = target_width - current_width - pad_left

        # Preallocate a padded matrix and insert the current matrix into it
        padded_matrix = np.zeros((target_height, target_width), dtype=matrix.dtype)
        padded_matrix[pad_top:pad_top + current_height,
        pad_left:pad_left + current_width] = matrix

        return padded_matrix

    return matrix


def convert_txt_to_png(input_txt, output_png, width_px, height_px, zoom_factor=1):
    """
    Converts a TXT file containing a binary matrix to a PNG image with transparency.

    :param input_txt: Path to the input TXT file
    :param output_png: Path to the output PNG file
    :param width_px: Width of the pattern PNG file in pixels
    :param height_px: Height of the pattern PNG file in pixels
    :param zoom_factor: Factor to zoom in the image by repeating pixels
    :return: Saves the PNG file at the specified path
    """

    matrix = read_txt_to_matrix(input_txt)

    assert isinstance(zoom_factor,
                      int) and zoom_factor > 0, "Zoom factor must be a positive integer."
    if height_px is None and width_px is None:
        height_px, width_px = get_matrix_size(matrix)
        height_px *= zoom_factor
        width_px *= zoom_factor
    else:
        assert isinstance(height_px, int) and height_px > 0, "Height must be a positive integer."
        assert isinstance(width_px, int) and width_px > 0, "Width must be a positive integer."

    matrix = zoom_in(matrix, zoom_factor)
    matrix = resize_with_crop_or_padding(matrix, width_px, height_px)
    matrix = apply_color_palette(matrix, COLOR_PALETTE)

    # Create a PIL image from the matrix
    image = Image.fromarray(matrix, mode='RGBA')

    # Save the image as PNG with transparency
    image.save(output_png)
    print(f"Pattern PNG saved to: {output_png} of size {image.size} px")
