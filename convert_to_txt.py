import argparse
from pattern_processing.eps_to_pattern import convert_eps_to_pattern


def main():
    parser = argparse.ArgumentParser(
        description="Convert an EPS file to a TXT file containing pattern data.")
    parser.add_argument("input_eps", type=str, help="Path to the input EPS file")
    parser.add_argument("output_txt", type=str, help="Path to the output TXT file")

    args = parser.parse_args()

    convert_eps_to_pattern(args.input_eps, args.output_txt)


if __name__ == "__main__":
    main()
