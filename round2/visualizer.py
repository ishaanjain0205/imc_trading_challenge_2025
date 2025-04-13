import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

if len(sys.argv) != 4:
    print("Usage: python visualize.py <csv_file> <x_column> <y_column>")
    sys.exit(1)

csv_file = sys.argv[1]
x_col = sys.argv[2]
y_col = sys.argv[3]

df = pd.read_csv(csv_file)

if x_col not in df.columns or y_col not in df.columns:
    print(f"Error: One or both columns '{x_col}', '{y_col}' not found in the file.")
    print("Available columns:", ", ".join(df.columns))
    sys.exit(1)

plt.figure(figsize=(10, 6))
plt.plot(df[x_col], df[y_col], marker='o')
plt.xlabel(x_col)
plt.ylabel(y_col)
plt.title(f"{y_col} vs {x_col}")
plt.grid(True)
plt.tight_layout()

base_name = os.path.splitext(os.path.basename(csv_file))[0]
plot_filename = f"{x_col}_{y_col}_{base_name}.png"

plt.savefig(plot_filename)
print(f"Plot saved as: {plot_filename}")

plt.show()
