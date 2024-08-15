import argparse
from pattern_processing.pattern_to_png import convert_txt_to_png


def main():
    parser = argparse.ArgumentParser(
        description="Convert a TXT file containing pattern data to a PNG image.")
    parser.add_argument("input_txt", type=str, help="Path to the input TXT file")
    parser.add_argument("output_png", type=str, help="Path to the output PNG file")
    parser.add_argument("--zoom_factor", type=int, default=1,
                        help="Factor to zoom in the image by repeating pixels (default: %(default)s)")

    args = parser.parse_args()

    convert_txt_to_png(args.input_txt, args.output_png, args.zoom_factor)


if __name__ == "__main__":
    main()
