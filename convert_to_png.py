import argparse
from pattern_processing.pattern_to_png import convert_txt_to_png


def main():
    parser = argparse.ArgumentParser(
        description="Convert a TXT file containing pattern data to a PNG image.")
    parser.add_argument("input_txt", type=str, help="Path to the input TXT file")
    parser.add_argument("output_png", type=str, help="Path to the output PNG file")

    args = parser.parse_args()

    convert_txt_to_png(args.input_txt, args.output_png)


if __name__ == "__main__":
    main()
