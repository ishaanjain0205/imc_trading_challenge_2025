import pandas as pd
import sys

if len(sys.argv) != 4:
    print("Usage: python combine_csvs.py file1.csv file2.csv file3.csv")
    sys.exit(1)

file1, file2, file3 = sys.argv[1], sys.argv[2], sys.argv[3]

df1 = pd.read_csv(file1)
df2 = pd.read_csv(file2)
df3 = pd.read_csv(file3)

combined_df = pd.concat([df1, df2, df3], ignore_index=True)

combined_df.to_csv("combined_output.csv", index=False)

print("Combined CSV saved as 'combined_output.csv'")
