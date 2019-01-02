# 
# @author: Allan
#

from tqdm import tqdm
from common.sentence import Sentence
from common.instance import Instance
from typing import List
import re

class Reader:


    def __init__(self, digit2zero:bool=True):
        self.digit2zero = digit2zero
        self.train_vocab = {}
        self.test_vocab = {}


    def read_from_file(self, file, number=-1, is_train=True):
        print("Reading file: " + file)
        insts = []
        # vocab = set() ## build the vocabulary
        with open(file, 'r', encoding='utf-8') as f:
            words = []
            labels = []
            for line in tqdm(f.readlines()):
                line = line.rstrip()
                if line == "":
                    insts.append(Instance(Sentence(words), labels))
                    words = []
                    labels = []
                    if len(insts) == number:
                        break
                    continue
                word, _, label = line.split()
                if self.digit2zero:
                    word = re.sub('\d', '0', word)
                words.append(word)
                if is_train:
                    self.train_vocab[word]=0
                else:
                    self.test_vocab[word]=0
                labels.append(label)
        return insts

    def read_conll(self, file: str, number: int = -1, is_train: bool = True) -> List[Instance]:
        print("Reading file: " + file)
        insts = []
        # vocab = set() ## build the vocabulary
        with open(file, 'r', encoding='utf-8') as f:
            words = []
            heads = []
            deps = []
            labels = []
            for line in tqdm(f.readlines()):
                line = line.rstrip()
                if line == "":
                    insts.append(Instance(Sentence(words, heads, deps), labels))
                    words = []
                    heads = []
                    deps = []
                    labels = []
                    if len(insts) == number:
                        break
                    continue
                vals = line.split()
                word = vals[1]
                head = int(vals[6])
                dep_label = vals[7]
                label = vals[10]
                if self.digit2zero:
                    word = re.sub('\d', '0', word) # replace digit with 0.
                words.append(word)
                heads.append(head - 1) ## because of 0-indexed.
                deps.append(dep_label)
                if is_train:
                    self.train_vocab[word]=0
                else:
                    self.test_vocab[word]=0
                labels.append(label)
        return insts


