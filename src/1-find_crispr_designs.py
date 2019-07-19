#!/usr/bin/env python3
from Bio.Seq import Seq
from Bio import SeqIO
import collections
import sys
import csv
import re
import os

# Jonathan Rodiger - 2019

# Perl like autovivification
def makehash():
    return collections.defaultdict(makehash)


# Loads chromosome sequence using fasta index + id mapping
def load_sequence(chr_id):
    return str(fasta_index[id_map[chr_id]].seq.upper())


# Builds chromosome to id mapping for species
def chr_id_mapping():
    chrom_map = {}
    mapfile = 'fasta_files/' + species + '_chr_ids.txt'
    with open(mapfile, 'r') as f:
        for line in f:
            data = line.strip('\n').split('\t')
            chrom_map[data[1]] = data[2]
    return chrom_map


# Returns all chromosomes + first and last snp in each from input
def get_chr_locs():
    chr_locs = {}
    with open(user_input, 'r') as f:
        for line in f:
            if header in line:
                continue
            data = line.split(',')
            chromosome = data[1]
            position = int(data[2])
            if chromosome not in chr_locs:
                chr_locs[chromosome] = [position, position]
            else:
                if chr_locs[chromosome][0] > position:
                    chr_locs[chromosome][0] = position
                if chr_locs[chromosome][1] < position:
                    chr_locs[chromosome][1] = position
    return chr_locs


# Returns list of snps that don't match the reference genome
def check_valid_SNPs():
    invalid_snps = []
    with open(user_input, 'r') as f:
        for line in f:
            if header in line:
                continue
            data       = line.strip().split(',')
            gene       = data[0]
            chromosome = data[1]
            snp_pos    = int(data[2])
            strand     = data[3]
            input_ref  = data[4].upper()
            input_var  = data[5].upper()
            start      = snp_pos - 11
            stop       = snp_pos + 10
            seq        = load_sequence(chromosome)
            if strand == '-':
                seq = str(Seq(seq).complement())
            try:
                ref = seq[snp_pos-1]
                if input_ref != ref:
                    invalid_snps.append(line)
                    with open('error.log', 'a') as out:
                        log_mismatch(out, gene, chromosome, snp_pos, strand, input_ref, input_var, start, stop)
                        out.write('Reference: ' + ref + ' (position: ' + str(snp_pos) + ') \n')
                        out.write('Surrounding region of reference: ' + seq[start:stop] 
                            + ' (Start: ' + str(start+1) + ', Stop: ' + str(stop) + ') \n\n\n')
            except IndexError:
                invalid_snps.append(line)
                with open('error.log', 'a') as out:
                    log_mismatch(out, gene, chromosome, snp_pos, strand, input_ref, input_var, start, stop)
                    out.write('---------------------------\n')
                    out.write('Warning index out of range\n')
                    out.write('---------------------------\n\n\n')
    return invalid_snps


# Write out information about input reference mismatch
def log_mismatch(file, gene, chromosome, snp_pos, strand, input_ref, input_var, start, stop):
    file.write('SNP does not match reference! Genome version might be different. \n\n')
    file.write('Input SNP: ' + input_ref + '>' + input_var + '\n')
    file.write('Chromosome: ' + chromosome + '\n')
    file.write('Gene: ' + gene + '\n')
    file.write('Position: ' + str(snp_pos) + '\n')
    file.write('Strand: ' + strand + '\n\n')
    file.write('Input: ' + input_ref + ' (position: ' + str(snp_pos) + ') \n')


# Returns list of SNPs of interest, giving results on both strands. 
def snp_list():
    snps = makehash()
    invalid_snps = check_valid_SNPs()
    with open(user_input, 'r') as f:
        for line in f:
            if line in invalid_snps or header in line:
                continue
            data       = line.strip().split(',')
            gene       = data[0]
            chromosome = data[1]
            position   = data[2]
            strand     = data[3]
            reference  = data[4].upper()
            variant    = data[5].upper()
            group      = data[6]
            if group != '':
                gene += ' (' + group + ')'
            snp = reference + '>' + variant
            rev = str(Seq(snp).complement())
            i = 0
            # seperate variants at same position w/ comma
            if strand == '+':
                if snps[chromosome][gene][int(position)]:
                    snps[chromosome][gene][int(position)]['+'] += ',' + variant
                    snps[chromosome][gene][int(position)]['-'] += ',' + str(Seq(variant).complement())
                else:
                    snps[chromosome][gene][int(position)] = {'+': snp, '-': rev}
            else:
                if snps[chromosome][gene][int(position)]:
                    snps[chromosome][gene][int(position)]['+'] += ',' + str(Seq(variant).complement())
                    snps[chromosome][gene][int(position)]['-'] += ',' + variant
                else:
                    snps[chromosome][gene][int(position)] = {'+': rev, '-': snp}
    return snps


# Returns list crispr designs (23-bp) found on either strand of sequence.
def get_kmers():
    crisprs = makehash()
    for chr_id in chr_locs:
        seq = load_sequence(chr_id)
        first_snp = chr_locs[chr_id][0]
        last_snp = chr_locs[chr_id][1]
        i = first_snp - 24
        while i < last_snp + 23:
            kmer = seq[i: i + 23]
            rev = str(Seq(kmer).reverse_complement())
            if check_terminator(kmer):
                crisprs[chr_id][i + 1] = [i + 23, kmer, '+']
            if check_terminator(rev):
                crisprs[chr_id][i + 23] = [i + 1, rev, '-']
            i += 1
    return crisprs


# Returns true if U6 terminator (TTTT) is not present.
def check_terminator(subseq):
    # Don't include PAM in search.
    m = re.search(regex, str(subseq))
    try:
        return 'TTTT' not in m.group(1)
    except AttributeError:
        return False


def print_crisprs():
    snps = snp_list()
    crisprs = get_kmers()
    global seq_permutations
    with open(outputfilename + '-snp_summary.csv', 'w') as output_file:
        output_file.write('gene,chromosome,start,end,strand,snp_pos,snp,wt_crispr,variant_crispr\n')
    # Create hashes so that each guide sequence is only printed once in FASTA file.
    wt_fasta = {}
    snp_fasta = {}
    for chr_id in chr_locs:
        for start_pos in sorted(crisprs[chr_id]):
            targets = makehash()
            end = crisprs[chr_id][start_pos][0]
            sequence = crisprs[chr_id][start_pos][1]
            strand = crisprs[chr_id][start_pos][2]
            for gene in snps[chr_id]:
                for position in sorted(snps[chr_id][gene]):
                    # skip designs in non-variable part of PAM
                    if strand == '+':
                        if position < start_pos or position > (end - 2):
                            continue
                        index = position - start_pos
                    else:
                        if position > start_pos or position < (end + 2):
                            continue
                        index = start_pos - position
                    targets[gene][index] = [
                        position,
                        snps[chr_id][gene][position][strand]
                    ]
            if not targets:
                continue
            for gene in targets:
                designs = {}
                bases = list(sequence)
                for pos in targets[gene]:
                    position, snp = targets[gene][pos]
                    ref, variant = str(snp).split('>')
                    if ',' in variant:
                        tmp = variant
                        variant = '[' + tmp + ']'
                    if not all_flag:
                        bases = list(sequence)
                    # Skip SNP-target if reference base doesn't match with actual base.
                    if bases[pos] != ref:
                        continue
                    bases[pos] = variant
                    variant_seqs = [''.join(bases)]
                    designs[position] = snp
                    if not all_flag:
                        # if design w/ multiple variants at same position, find all permutations
                        if ',' in variant_seqs[0]:
                            seq_permutations = []
                            find_permutations(variant_seqs[0])
                            variant_seqs = seq_permutations
                        for variant_seq in variant_seqs:
                            if check_terminator(variant_seq):
                                with open(outputfilename + '-snp_summary.csv', 'a') as out:
                                    out.write(gene + ',' + chr_id + ',' + str(start_pos) + ',' + str(end) + ',' 
                                            + strand + ',' + str(position) + ',' + snp[0:2] 
                                            # check which variant at snp position for current snp design
                                            + variant_seq[abs(start_pos-position)] + ',' + str(sequence) + ',' 
                                            + variant_seq + '\n')
                                snp_fasta[variant_seq] = None
                                wt_fasta[sequence] = None
                if all_flag:
                    snp_pos = designs.keys()
                    variant_seqs = [''.join(bases)]
                    # if design w/ multiple variants at same position, find all permutations
                    if ',' in variant_seqs[0]:
                        seq_permutations = []
                        find_permutations(variant_seqs[0])
                        variant_seqs = seq_permutations
                    for variant_seq in variant_seqs:
                        if check_terminator(variant_seq):
                            with open(outputfilename + '-snp_summary.csv', 'a') as out:
                                out.write(gene + ',' + chr_id + ',' + str(start_pos) + ',' + str(end) + ','
                                        + strand + ',' + ';'.join(str(v) for v in snp_pos) + ','
                                        # check which variant at each position for current snp design
                                        + ';'.join(str(designs[v][0:2] + variant_seq[abs(start_pos-v)]) for v in snp_pos) 
                                        + ',' + str(sequence) + ',' + variant_seq + '\n')
                            snp_fasta[variant_seq] = None
                            wt_fasta[sequence] = None
    # Print FASTA files for BLAST in next step.
    print_fasta(wt_fasta, outputfilename + '-designs_wt.fasta')
    print_fasta(snp_fasta, outputfilename + '-designs_snp.fasta')


# Finds all permutations of sequence w/ multiple variants at same position
# Ex: 'C[A,T]CCGGAAAAGCTCCGCTTTT[G,C]G' -> 
# 'CACCGGAAAAGCTCCGCTTTTGG', 'CACCGGAAAAGCTCCGCTTTTCG', 
# 'CTCCGGAAAAGCTCCGCTTTTGG', 'CTCCGGAAAAGCTCCGCTTTTCG'
def find_permutations(design):
    input_seq   = ''
    variants    = []
    variant_pos = []
    start_stop  = []
    # store multi variant locs
    j = 0
    for i in range(0, len(design)):
        if design[i] == '[':
            start_stop.append([i])
        elif design[i] == ']':
            start_stop[j].append(i)
            j += 1
    # convert [...] to N
    gap = False
    for pos in design:
        if pos == '[':
            gap = True
            input_seq += 'N'
        elif pos == ']':
            gap = False
        elif not gap:
            input_seq += pos
    # store alternates for each variable N position in design
    j = 0
    for i in range(0, len(input_seq)):
        if input_seq[i] == 'N':
            variants.append(design[start_stop[j][0]+1:start_stop[j][1]].split(','))
            variant_pos.append(i)
            j += 1
    recursive_permutations('', variants, variant_pos, 0, input_seq)


def recursive_permutations(seq, variants, variant_pos, k, input_seq):
    if k == len(variants):
        output_seq = list(input_seq)
        i = 0
        for pos in variant_pos:
            output_seq[pos] = seq[i]
            i += 1
        output_seq = ''.join(output_seq)
        global seq_permutations
        seq_permutations.append(output_seq)
    else:
        for nuc in variants[k]:
            recursive_permutations(seq + nuc, variants, variant_pos, k + 1, input_seq)


def print_fasta(designs, filename):
    if designs:
        with open(filename, 'a') as output_file:
            for seq in designs.keys():
                output_file.write('>' + str(seq) + '\n')
                output_file.write(str(seq) + '\n')


if __name__ == '__main__':
    # Read in command line arguments
    if len(sys.argv) != 5 and len(sys.argv) != 6:
        print('Usage: ./snp_crispr.sh <species> <input_file> <PAM> <all>')
        exit()
    species = sys.argv[1]
    user_input = sys.argv[2]
    outputfilename = sys.argv[3]
    pam = sys.argv[4]
    all_flag = False
    if len(sys.argv) == 6:
        if sys.argv[5] == '-all':
            all_flag = True

    # globals
    header = 'gene_symbol,chromosome,position,strand,reference,variant,group(optional)'
    fasta_index = SeqIO.index('fasta_files/' + species + '.fasta', 'fasta')
    id_map = chr_id_mapping()
    chr_locs = get_chr_locs()
    seq_permutations = []

    # set regex for chosen PAM
    if pam == '-NGG':
        regex = r'([ACGT]{20})[ACGT]GG'
    elif pam == '-NAG':
        regex = r'([ACGT]{20})[ACGT]AG'
    else:
        raise ValueError('invalid pam')

    print_crisprs()
