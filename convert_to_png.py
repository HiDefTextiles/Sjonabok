import argparse
from pattern_processing.pattern_to_png import convert_txt_to_png


def main():
    parser = argparse.ArgumentParser(
        description="Convert a TXT file containing pattern data to a PNG image.")
    parser.add_argument("input_txt", type=str, help="Path to the input TXT file")
    parser.add_argument("output_png", type=str, help="Path to the output PNG file")
    parser.add_argument("--zoom_factor", type=int, default=1,
                        help="Factor to zoom in the image by repeating pixels (default: %(default)s)")
    parser.add_argument("--width_px", type=int)
    parser.add_argument("--height_px", type=int)

    args = parser.parse_args()

    convert_txt_to_png(
        input_txt=args.input_txt,
        output_png=args.output_png,
        height_px=args.height_px,
        width_px=args.width_px,
        zoom_factor=args.zoom_factor)


if __name__ == "__main__":
    main()
