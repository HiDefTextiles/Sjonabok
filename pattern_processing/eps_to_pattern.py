# eps_to_pattern.py

from PIL import Image
import os
import json
from collections import Counter
import numpy as np


def convert_eps_to_pattern(input_eps, output_txt):
    '''
    Use: convert_eps_to_pattern(input_eps, output_txt)
    :param input_eps: Filepath to Sjónabók EPS file
    :param output_txt: A simplified pattern in TXT format
    :return: saves a simplified pattern in TXT format
    '''

    with Image.open(os.path.expanduser(input_eps)) as source:
        rgba = source.convert('RGBA')
        background = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
        rgb = np.asarray(Image.alpha_composite(background, rgba).convert('RGB'))

    matrix, colors = simplify_color_matrix(rgb)
    delimiter = '' if int(matrix.max(initial=0)) < 10 else ' '
    np.savetxt(output_txt, matrix, fmt='%d', delimiter=delimiter)

    if len(colors) > 1:
        palette_path = os.path.splitext(output_txt)[0] + '.palette.json'
        with open(palette_path, 'w', encoding='utf-8') as palette_file:
            json.dump({'colors': colors}, palette_file, ensure_ascii=False, indent=2)


def convert_image_to_binary_matrix(image_path, threshold=240):
    '''
    Use: matrix = convert_image_to_binary_matrix(image_path)
    Pre: image_path is the path to the image to convert
    Post: matrix is a binary numpy matrix of the image where 1 represents black
          pixels and 0 represents white. threshold ATH skrifa meira um 
    '''
    image_path = os.path.expanduser(image_path)
    image = Image.open(image_path)

    # Convert to grayscale and apply threshold
    image = image.convert('L')
    image = image.point(lambda p: p > threshold and 255)
    image = image.convert('1')  # Convert to 1-bit pixels, black and white

    # Create matrix of 1s and 0s
    width, height = image.size
    matrix = []

    for y in range(height):
        row = []
        for x in range(width):
            pixel = image.getpixel((x, y))
            row.append(1 if pixel == 0 else 0)  # 1 for black, 0 for white 
        matrix.append(row)

    return np.array(matrix)


def get_grid_layout(matrix):
    '''
    Use: rows,cols = get_grid_layout(matrix)
    Pre: matrix is a binary pattern matrix on a grid where it is assumed
         that each grid line has the width one row/column in the matrix.
    Post: rows, cols contain the indexes of each grid row and column of matrix.
    '''
    def long_lines(profile):
        candidates = np.flatnonzero(profile >= max(0.8, profile.max() * 0.9))
        groups = []
        for index in candidates:
            if groups and index <= groups[-1][-1] + 1:
                groups[-1].append(int(index))
            else:
                groups.append([int(index)])
        return [group[-1] for group in groups]

    rows = long_lines(np.mean(matrix, axis=1))
    cols = long_lines(np.mean(matrix, axis=0))

    # Retain the original edge-based method for EPS files whose grid does not
    # span most of the raster (for example, a chart surrounded by margins).
    if len(rows) < 3 or len(cols) < 3:
        rows = []
        cols = []
        n, m = matrix.shape
        for i in range(n):
            if np.sum(matrix[i, 0:4]) >= 3:
                rows.append(i)
        for j in range(m):
            if np.sum(matrix[0:4, j]) >= 3:
                cols.append(j)
    return rows, cols


def remove_grid(matrix):
    '''
    Use: no_grid_matrix = remove_grid(matrix)
    Pre: matrix is a binary pattern on a grid where 1 represents black pixels
         and 0 white pixels. It is assumed that the width of each grid line takes
         up one column or row in matrix.
    Post: no_grid_matrix is the same as matrix except all grid lines have been set to 
          zero.
    '''
    grid_rows, grid_cols = get_grid_layout(matrix)
    matrix[grid_rows, :] = 0
    matrix[:, grid_cols] = 0
    return matrix


def remove_outside_of_pattern(matrix, grid_rows, grid_cols, return_bounds=False):  # and update grid indx
    '''
    Use: new_matrix, updated_grid_rows, update_grid_cols = remove_outside_of_pattern(matrix,grid_rows,grid_cols)
    Pre: matrix is a numpy matrix binary pattern on a grid where 1 represents black pixels and 0 white pixels. It is assumed
         that the width of each grid line takes up one column or row in matrix and that each grid line has been
         set to 0. grid_rows is a list that contains the indexes of each horizontal grid line and grid_cols is a list that
         has the indexes of each vertical line. Both list must be sorted from smallest to largest.
    Post: new_matrix still has the binary pattern but has the width of the largest horizontal line of the pattern and the
          height of the largest vertical line of the pattern. updated_grid_rows and updated_grid_cols are lists that contain
          the grid line indexes of new_matrix in ascending order.
    '''
    min_pixels_in_boundary = 5
    top, bottom, left, right = -1, -1, -1, -1

    # slice off right side
    while right == -1:
        r = grid_cols[-1]
        if np.sum(matrix[:, r - 1]) >= min_pixels_in_boundary:
            matrix = matrix[:, :r - 1]
            right = r
        grid_cols = grid_cols[:-1]

    # slice off bottom
    while bottom == -1:
        b = grid_rows[-1]
        if np.sum(matrix[b - 1, :]) >= min_pixels_in_boundary:
            matrix = matrix[:b - 1, :]
            bottom = b
        grid_rows = grid_rows[:-1]

    # slice off left side
    while left == -1:
        l = grid_cols[0]
        if np.sum(matrix[:, l + 1]) >= min_pixels_in_boundary:
            matrix = matrix[:, l + 1:]
            left = l
        grid_cols = grid_cols[1:]
    column_offset = l + 1 if return_bounds else l
    grid_cols = [x - column_offset for x in grid_cols]  # update indices of grid columns

    # slice off bottom
    while top == -1:
        t = grid_rows[0]
        if np.sum(matrix[t + 1, :]) >= min_pixels_in_boundary:
            matrix = matrix[t + 1:, :]
            top = t
        grid_rows = grid_rows[1:]
    row_offset = t + 1 if return_bounds else t
    grid_rows = [x - row_offset for x in grid_rows]  # update indices of grid rows

    if top >= bottom or left >= right:
        raise ValueError('removing the outside of pattern went wrong')

    if return_bounds:
        # The slices above remove the outer grid rules themselves.
        return matrix, grid_rows, grid_cols, (t + 1, b - 1, l + 1, r - 1)
    return matrix, grid_rows, grid_cols


def _find_regular_grid_cells(gray):
    """Find regular gray chart rules in rasterized book-page screenshots."""
    rule_pixels = ((gray >= 130) & (gray <= 210)).astype(float)
    row_profile = rule_pixels.mean(axis=1)
    col_profile = rule_pixels.mean(axis=0)

    def find_lines(profile):
        candidates = np.flatnonzero(profile >= 0.35)
        groups = np.split(candidates, np.flatnonzero(np.diff(candidates) > 1) + 1)
        groups = [group for group in groups if len(group)]
        if len(groups) < 8:
            return None
        positions = [int(group[np.argmax(profile[group])]) for group in groups]
        gaps = [right - left for left, right in zip(positions, positions[1:])
                if 5 <= right - left <= 60]
        if not gaps:
            return None
        period = Counter(gaps).most_common(1)[0][0]
        # The first rule is a strong registration point; later antialiased
        # rules can shift by a pixel, so do not infer phase from every peak.
        return list(range(positions[0], positions[-1] + 1, period))

    rows, cols = find_lines(row_profile), find_lines(col_profile)
    if rows and cols:
        return rows, cols
    return None


def simplify_color_matrix(rgb_matrix, threshold=240):
    """Reduce a colour or symbol chart to one integer code per cell.

    The geometric grid is detected from a grayscale ink mask, while the
    source RGB values and glyph shapes are sampled inside each cell. Similar
    antialiased RGB values and repeated glyphs are grouped. Code 0 is the
    empty/background cell; each foreground colour/symbol combination gets
    its own integer code.
    """
    gray = np.asarray(Image.fromarray(rgb_matrix).convert('L'))
    regular_cells = _find_regular_grid_cells(gray)
    binary = (gray <= threshold).astype(np.uint8)
    if regular_cells:
        row_lines, col_lines = regular_cells
        cell_bounds = [(row_lines[i] + 1, row_lines[i + 1],
                        col_lines[j] + 1, col_lines[j + 1])
                       for i in range(len(row_lines) - 1)
                       for j in range(len(col_lines) - 1)]
        matrix_shape = (len(row_lines) - 1, len(col_lines) - 1)
    else:
        grid_rows, grid_cols = get_grid_layout(binary)
        if len(grid_rows) < 3 or len(grid_cols) < 3:
            raise ValueError('Could not identify a complete chart grid in the EPS image')
        if (len(grid_rows) > binary.shape[0] // 4 or
                len(grid_cols) > binary.shape[1] // 4):
            raise ValueError('Could not distinguish chart rules from dense chart artwork')
        without_grid = remove_grid(binary.copy())
        cropped_binary, grid_rows, grid_cols, bounds = remove_outside_of_pattern(
            without_grid, list(grid_rows), list(grid_cols), return_bounds=True)
        top, bottom, left, right = bounds
        rgb_matrix = rgb_matrix[top:bottom, left:right]
        n, m = cropped_binary.shape
        grid_rows = [0] + grid_rows + [n]
        grid_cols = [0] + grid_cols + [m]
        cell_bounds = [(grid_rows[i], grid_rows[i + 1], grid_cols[j], grid_cols[j + 1])
                       for i in range(len(grid_rows) - 1)
                       for j in range(len(grid_cols) - 1)]
        matrix_shape = (len(grid_rows) - 1, len(grid_cols) - 1)

    records = []
    for index, (y0, y1, x0, x1) in enumerate(cell_bounds):
        row, col = divmod(index, matrix_shape[1])
        interior = rgb_matrix[y0:y1, x0:x1]
        if interior.size == 0:
            continue
        ink = np.linalg.norm(interior.astype(float) - 255.0, axis=2) > 40
        pixels = interior[ink]
        if len(pixels) < max(3, int(interior.shape[0] * interior.shape[1] * 0.01)):
            continue
        # Coarse quantisation absorbs edge antialiasing without merging
        # clearly distinct yarn or symbol colours.
        quantized = (pixels // 16) * 16
        unique, counts = np.unique(quantized, axis=0, return_counts=True)
        sample = unique[int(np.argmax(counts))].astype(float)
        ys, xs = np.where(ink)
        glyph = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        scale = min(12 / glyph.shape[0], 12 / glyph.shape[1])
        glyph_size = (max(1, round(glyph.shape[1] * scale)),
                      max(1, round(glyph.shape[0] * scale)))
        glyph_image = Image.fromarray((glyph * 255).astype(np.uint8)).resize(
            glyph_size, Image.Resampling.NEAREST)
        signature = np.zeros((16, 16), dtype=bool)
        left_pad = (16 - glyph_size[0]) // 2
        top_pad = (16 - glyph_size[1]) // 2
        signature[top_pad:top_pad + glyph_size[1],
                  left_pad:left_pad + glyph_size[0]] = np.asarray(glyph_image) > 127
        records.append({'row': row, 'col': col, 'color': sample,
                        'signature': signature, 'density': float(ink.mean())})

    if not records:
        raise ValueError('No filled chart cells were found')

    grayscale_source = np.median([
        max(record['color']) - min(record['color']) for record in records
    ]) < 18
    centers = []
    for record in records:
        sample = record['color']
        if grayscale_source:
            record['color_class'] = 0
            continue
        distances = [np.linalg.norm(sample - center) for center in centers]
        if not distances or min(distances) > 48:
            centers.append(sample.copy())
            record['color_class'] = len(centers) - 1
        else:
            record['color_class'] = int(np.argmin(distances))

    matrix = np.zeros(matrix_shape, dtype=np.int16)
    shape_centers = {}
    class_codes = {}
    for record in records:
        color_class = record['color_class']
        candidates = shape_centers.setdefault(color_class, [])
        signature = record['signature']
        distances = []
        for center in candidates:
            union = np.logical_or(signature, center).sum()
            intersection = np.logical_and(signature, center).sum()
            distances.append(1.0 - intersection / max(1, union))
        if not distances or min(distances) > 0.65:
            candidates.append(signature)
            symbol_class = len(candidates) - 1
        else:
            symbol_class = int(np.argmin(distances))
        key = (color_class, symbol_class)
        if key not in class_codes:
            class_codes[key] = len(class_codes) + 1
        matrix[record['row'], record['col']] = class_codes[key]

    colors = []
    if len(centers) > 1:
        for (color_class, shape_class), value in class_codes.items():
            center = centers[color_class]
            rgb = [int(min(255, max(0, channel + 8))) for channel in center]
            colors.append({'value': value, 'rgb': rgb, 'shape_class': shape_class})
    return matrix, colors


def simplify_binary_matrix(Matrix):
    '''
    Use:   simplified_matrix = simplify_binary_matrix(Matrix)
    Pre:   Matrix is a binary matrix of a cross stich pattern on a grid where 1 represents
           black and 0 represents white. It is assumed that each horizontal/vertical line
           of the grid only takes up one row/column in Matrix.
    Post:  simplified_matrix is a simplified binary pattern matrix of Matrix such that 1 represents
           a cross in a grid cell and 0 represents no cross in a grid cell. The grid has been removed
           in simplified_matrix and the height and with of simplified matrix is the same as the
           maximum number of horizontal and vertical crosses in Matrix.
    '''
    grid_rows, grid_cols = get_grid_layout(Matrix)
    matrix = remove_grid(Matrix)
    matrix, grid_rows, grid_cols = remove_outside_of_pattern(matrix, grid_rows, grid_cols)
    n, m = matrix.shape

    min_prop = 0.5  # minumum proportion of 1s in a cell to define a cross

    grid_rows.insert(0, 0)
    grid_rows.append(n)
    grid_cols.insert(0, 0)
    grid_cols.append(m)
    simplified_matrix = np.zeros((len(grid_rows) - 1, len(grid_cols) - 1))
    for i in range(len(grid_rows) - 1):  # go through each cell and find all crosses
        cell_top = grid_rows[i]  # define cell boundaries
        cell_bottom = grid_rows[i + 1]
        for j in range(len(grid_cols) - 1):
            cell_left = grid_cols[j]
            cell_right = grid_cols[j + 1]
            cell = matrix[cell_top:cell_bottom, cell_left:cell_right]
            a, b = cell.shape

            prop = np.sum(cell) / (a * b)
            if prop >= min_prop:
                simplified_matrix[i, j] = 1

    return simplified_matrix
