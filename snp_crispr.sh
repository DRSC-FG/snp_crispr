#!/bin/bash

# arguments
species=$1
input=$2
pam=$3
all=$4

# paths
outputfilename="designs"
wt="tmp/$outputfilename-wt.fasta"
snp="tmp/$outputfilename-snp.fasta"
blast_wt="tmp/$outputfilename-wt_blast.txt"
blast_snp="tmp/$outputfilename-snp_blast.txt"

# run pipeline + check for errors
rm error.log 2>/dev/null
python src/1-find_crispr_designs.py $species $input tmp/$outputfilename $pam $all
perl src/2-blast_crisprs.pl -s $species -f1 $wt -f2 $snp -o tmp/$outputfilename -pam $pam
perl src/3-calculate_scores.pl -b1 $blast_wt -b2 $blast_snp -out results/$outputfilename
python src/4-process_results.py $blast_wt $blast_snp results/$outputfilename
cat error.log 2>/dev/null
