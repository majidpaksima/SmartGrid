import sys


class Console:
    @staticmethod
    def print_banner():
        banner = [
            "========================================",
            "  Multi-Symbol Smart ATR Grid Bot",
            "  Python + MetaTrader 5",
            "========================================",
        ]
        for line in banner:
            print(line)

    @staticmethod
    def print_separator(char: str = "-", length: int = 50):
        print(char * length)

    @staticmethod
    def ask_yes_no(prompt: str, default: bool = True) -> bool:
        default_str = "Y/n" if default else "y/N"
        full_prompt = f"{prompt} [{default_str}]: "
        try:
            response = input(full_prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if response == "":
            return default
        return response in ("y", "yes")

    @staticmethod
    def ask_input(prompt: str, default: str = "") -> str:
        if default:
            full_prompt = f"{prompt} [{default}]: "
        else:
            full_prompt = f"{prompt}: "
        try:
            response = input(full_prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if response == "":
            return default
        return response

    @staticmethod
    def ask_int(prompt: str, default: int, min_val: int = 1, max_val: int = 100) -> int:
        while True:
            raw = Console.ask_input(prompt, str(default))
            try:
                val = int(raw)
                if min_val <= val <= max_val:
                    return val
                print(f"Value must be between {min_val} and {max_val}.")
            except ValueError:
                print("Please enter a valid integer.")

    @staticmethod
    def ask_float(prompt: str, default: float, min_val: float = 0.0, max_val: float = 1e9) -> float:
        while True:
            raw = Console.ask_input(prompt, str(default))
            try:
                val = float(raw)
                if min_val <= val <= max_val:
                    return val
                print(f"Value must be between {min_val} and {max_val}.")
            except ValueError:
                print("Please enter a valid number.")

    @staticmethod
    def ask_option(prompt: str, options: list, default: int = 1) -> int:
        print(prompt)
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            raw = Console.ask_input("Select an option", str(default))
            try:
                val = int(raw)
                if 1 <= val <= len(options):
                    return val
                print(f"Please select a number between 1 and {len(options)}.")
            except ValueError:
                print("Please enter a valid number.")

    @staticmethod
    def print_table(headers: list, rows: list):
        if not rows:
            return
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
        print(header_line)
        print(sep_line)
        for row in rows:
            print(" | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(row)))
