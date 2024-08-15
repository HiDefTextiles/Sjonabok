import argparse
from pattern_processing.separate_patterns import split_patterns


def main():
    parser = argparse.ArgumentParser(
        description="Split a TXT file into sub-patterns based on the distance between rows and "
                    "columns.")
    parser.add_argument("input_txt", type=str, help="Path to the input TXT file")
    parser.add_argument("--cols_distance", type=int, default=5,
                        help="Distance between columns (default: %(default)s")
    parser.add_argument("--rows_distance", type=int, default=5,
                        help="Distance between rows (default: %(default)s")

    args = parser.parse_args()

    num_patterns = split_patterns(args.input_txt, args.rows_distance, args.cols_distance)
    if num_patterns == 0:
        print("No sub-patterns created.")
    else:
        print(f"Number of sub-patterns created: {num_patterns}")


if __name__ == "__main__":
    main()
