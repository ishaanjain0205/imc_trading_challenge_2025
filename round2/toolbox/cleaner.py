import pandas as pd
import os
import sys

if len(sys.argv) < 2:
    print("Usage: python clean_csv.py <path_to_csv_file>")
    sys.exit(1)

file1 = sys.argv[1]

df = pd.read_csv(file1, delimiter=';')

df.fillna(0, inplace=True)

output_file = file1.replace('.csv', '_commas_cleaned.csv')
df.to_csv(output_file, index=False)

print(f"Full cleaned file saved as: {output_file}")

if 'product' not in df.columns:
    print("Error: 'product' column not found in CSV.")
else:
    base_dir = os.path.dirname(file1)
    product_dir = os.path.join(base_dir, 'by_product')
    os.makedirs(product_dir, exist_ok=True)

    for product_name, product_df in df.groupby('product'):
        safe_name = str(product_name).replace(" ", "_").replace("/", "_")
        product_path = os.path.join(product_dir, f"{safe_name}.csv")
        product_df.to_csv(product_path, index=False)
        print(f"Saved file for product '{product_name}': {product_path}")
