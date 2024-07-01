import argparse
from PIL import Image
import os
import numpy as np
from collections import Counter
import matplotlib.pyplot as plt
import cv2
from pathlib import Path



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
    rows = []
    cols = []
    n,m = matrix.shape

    #get grid row indexes
    for i in range(n):
        if np.sum(matrix[i,0:4]) >= 3: #if mostly zeros we have a grid line
            rows.append(i)
    
    for j in range(m):
        if np.sum(matrix[0:4,j]) >= 3:
            cols.append(j)
    return rows,cols


def remove_grid(matrix):
    '''
    Use: no_grid_matrix = remove_grid(matrix)
    Pre: matrix is a binary pattern on a grid where 1 represents black pixels
         and 0 white pixels. It is assumed that the width of each grid line takes
         up one column or row in matrix.
    Post: no_grid_matrix is the same as matrix except all grid lines have been set to 
          zero.
    '''
    grid_rows,grid_cols = get_grid_layout(matrix)
    matrix[grid_rows,:]=0
    matrix[:,grid_cols]=0
    return matrix

def remove_outside_of_pattern(matrix, grid_rows, grid_cols): #and update grid indx
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

    #slice off right side
    while right == -1:
        r = grid_cols[-1]
        if np.sum(matrix[:,r-1]) >= min_pixels_in_boundary:
            matrix = matrix[:,:r-1]
            right = r
        grid_cols = grid_cols[:-1]
    

    #slice off bottom
    while bottom == -1:
        b = grid_rows[-1]
        if np.sum(matrix[b-1,:]) >= min_pixels_in_boundary:
            matrix = matrix[:b-1,:]
            bottom = b
        grid_rows = grid_rows[:-1]

    #slice off left side
    while left == -1:
        l = grid_cols[0]
        if np.sum(matrix[:,l+1]) >= min_pixels_in_boundary:
            matrix = matrix[:,l+1:]
            left = l
        grid_cols = grid_cols[1:]
    grid_cols = [x-l for x in grid_cols] #update indices of grid columns

    #slice off bottom
    while top == -1:
        t = grid_rows[0]
        if np.sum(matrix[t+1,:]) >= min_pixels_in_boundary:
            matrix = matrix[t+1:,:]
            top = t
        grid_rows = grid_rows[1:]
    grid_rows = [x-t for x in grid_rows] #update indices of grid rows

    if top >= bottom or left >= right:
        raise ValueError('removing the outside of pattern went wrong')
    
    return matrix,grid_rows,grid_cols
    



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
    grid_rows,grid_cols = get_grid_layout(Matrix)
    matrix = remove_grid(Matrix)
    matrix,grid_rows,grid_cols = remove_outside_of_pattern(matrix,grid_rows,grid_cols)
    n,m = matrix.shape

    min_prop = 0.5 #minumum proportion of 1s in a cell to define a cross

    grid_rows.insert(0,0)
    grid_rows.append(n)
    grid_cols.insert(0,0)
    grid_cols.append(m)
    simplified_matrix = np.zeros((len(grid_rows)-1,len(grid_cols)-1))
    for i in range(len(grid_rows)-1): #go through each cell and find all crosses
        cell_top = grid_rows[i] #define cell boundaries
        cell_bottom = grid_rows[i+1]
        for j in range(len(grid_cols)-1):
            cell_left = grid_cols[j]
            cell_right = grid_cols[j+1]
            cell = matrix[cell_top:cell_bottom,cell_left:cell_right]
            a,b = cell.shape

            prop = np.sum(cell)/(a*b)
            if prop >= min_prop:
                simplified_matrix[i,j] = 1
    
    return simplified_matrix
            

def main():
    '''
    provided with the path to the folder for the Islensk Sjonabok the function creates two folders
    under each chapter where each pattern in the chapter is converted to a matrix saved as a text file and
    a png file.
    '''
    parser = argparse.ArgumentParser(
        description="convert EPS patterns to PNG and txt files")
    parser.add_argument("sjonabok_path", help="Path to the Sjonabok folder")

    args = parser.parse_args()

    #list all folders/chapters in the Sjonabok folder
    chapters = []
    try:
        dir = Path(args.sjonabok_path)
        for entry in dir.iterdir():
            if entry.is_dir():
                chapters.append(entry)
    except Exception as e:
        print(f"Error: {e}")


    # go through each eps file in each chapter and save a png file
    for chapter in chapters:
        print(f"starting on chapter {chapter.name}")
        png_path = chapter/"png"
        npy_path = chapter/"npy_txt"
        if not os.path.exists(png_path): #create folder to store png patterns
            os.makedirs(png_path)
        if not os.path.exists(npy_path): #create folder to store npy patterns
            os.makedirs(npy_path)

        eps_path = chapter/"eps" #path to the eps folder

        #for each file in eps folder convert to png and txt file and store it
        try:
            for file_path in eps_path.iterdir():
                if file_path.is_file():
                    print(f"converting pattern {file_path.stem}")
                    matrix = convert_image_to_binary_matrix(file_path)
                    matrix = simplify_binary_matrix(matrix)
                    png_file_name = file_path.stem + ".png"
                    npy_file_name = file_path.stem + ".txt"
                    png_file_path = png_path/png_file_name
                    npy_file_path = npy_path/npy_file_name
                    cv2.imwrite(png_file_path, (1-matrix) * 255)
                    np.savetxt(npy_file_path, matrix, fmt='%d')
        
        except Exception as e:
            print(f"Error: {e}")



if __name__ == "__main__":
    main()

