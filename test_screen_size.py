#!/usr/bin/env python3
"""
Screen Size Diagnostic Tool
Shows row and column numbers to determine actual visible terminal size.
"""

import curses


def main(stdscr):
    curses.curs_set(0)
    stdscr.clear()

    height, width = stdscr.getmaxyx()

    # Draw column numbers VERTICALLY at every 10 columns
    for col in range(10, width - 1, 10):
        num_str = str(col)
        for i, digit in enumerate(num_str):
            if i < height:
                try:
                    stdscr.addch(i, col, digit)
                except curses.error:
                    pass

    # Draw row numbers HORIZONTALLY at every 10 rows
    for row in range(10, height, 10):
        num_str = str(row)
        for i, digit in enumerate(num_str):
            if i < width - 1:
                try:
                    stdscr.addch(row, i, digit)
                except curses.error:
                    pass

    # Fill rest with grid pattern
    for row in range(height):
        for col in range(width - 1):
            try:
                is_col_number_area = (col % 10 == 0 and col > 0 and row < len(str(col)))
                is_row_number_area = (row % 10 == 0 and row > 0 and col < len(str(row)))

                if is_col_number_area or is_row_number_area:
                    continue

                if row % 10 == 0 and col % 10 == 0:
                    stdscr.addch(row, col, '+')
                elif row % 10 == 0:
                    stdscr.addch(row, col, '-')
                elif col % 10 == 0:
                    stdscr.addch(row, col, '|')
                else:
                    stdscr.addch(row, col, '.')
            except curses.error:
                pass

    # LABEL SPECIFIC ROWS AT THE BOTTOM to see which are visible
    # Write row labels on the RIGHT side of screen for last several rows
    label_col = 5
    for offset in range(10):
        row = height - 1 - offset
        if row >= 0:
            label = f"ROW {row} (h-{offset+1})"
            try:
                stdscr.addstr(row, label_col, label, curses.A_REVERSE)
            except curses.error:
                pass

    # Show detected size at top
    msg1 = f"Detected: {width} cols x {height} rows"
    msg2 = f"Footer would be at row {height - 2} (height-2)"
    msg3 = "Which ROW labels can you see at bottom?"
    msg4 = "Press 'q' to quit"

    try:
        stdscr.addstr(2, 20, msg1, curses.A_BOLD)
        stdscr.addstr(3, 20, msg2, curses.A_BOLD)
        stdscr.addstr(4, 20, msg3, curses.A_BOLD)
        stdscr.addstr(5, 20, msg4, curses.A_BOLD)
    except curses.error:
        pass

    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key == ord('q') or key == 27:
            break


if __name__ == "__main__":
    try:
        curses.wrapper(main)
        print("\nScreen Size Test Complete!")
        print("Which was the LOWEST 'ROW X' label you could see?")
        print("That tells us the actual last visible row.")
    except KeyboardInterrupt:
        pass
