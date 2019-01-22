
import argparse
import random
import numpy as np
from config.config import Config
from config.reader import Reader
from config import eval
from config.config import Config
import time
from pytorch_model.pytorch_lstmcrf import NNCRF
import torch
import torch.optim as optim
import torch.nn as nn
from config.utils import lr_decay, simple_batching
from typing import List
from common.instance import Instance
from termcolor import colored


def setSeed(opt, seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if opt.device.startswith("cuda"):
        print("using GPU...", torch.cuda.current_device())
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def parse_arguments(parser):
    parser.add_argument('--mode', type=str, default='train')
    parser.add_argument('--device', type=str, default="cuda:0")
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--digit2zero', action="store_true", default=True)
    parser.add_argument('--dataset', type=str, default="abc")
    parser.add_argument('--embedding_file', type=str, default="data/glove.6B.100d.txt")
    # parser.add_argument('--embedding_file', type=str, default=None)
    parser.add_argument('--embedding_dim', type=int, default=100)
    parser.add_argument('--optimizer', type=str, default="adam")
    parser.add_argument('--learning_rate', type=float, default=0.015) ##only for sgd now
    parser.add_argument('--momentum', type=float, default=0.0)
    parser.add_argument('--l2', type=float, default=1e-8)
    parser.add_argument('--lr_decay', type=float, default=0.05)
    parser.add_argument('--batch_size', type=int, default=2)
    parser.add_argument('--num_epochs', type=int, default=100)

    ##model hyperparameter
    parser.add_argument('--hidden_dim', type=int, default=200, help="hidden size of the LSTM")
    parser.add_argument('--dep_emb_size', type=int, default=50, help="embedding size of dependency")
    parser.add_argument('--dropout', type=float, default=0.5, help="dropout for embedding")
    # parser.add_argument('--tanh_hidden_dim', type=int, default=100)
    parser.add_argument('--use_char_rnn', type=int, default=1, choices=[0, 1], help="use character-level lstm, 0 or 1")
    parser.add_argument('--use_head', type=int, default=0, choices=[0, 1], help="not use dependency")

    parser.add_argument('--use_elmo', type=int, default=0, choices=[0, 1], help="use Elmo embedding or not")

    # parser.add_argument('--use2layerLSTM', type=int, default=0, choices=[0, 1], help="use 2 layer bilstm")
    parser.add_argument('--second_hidden_size', type=int, default=0, help="hidden size for 2nd bilstm layer")

    parser.add_argument('--train_num', type=int, default=-1)
    parser.add_argument('--dev_num', type=int, default=-1)
    parser.add_argument('--test_num', type=int, default=-1)
    parser.add_argument('--eval_freq', type=int, default=4000,help="evaluate frequency (iteration)")
    parser.add_argument('--eval_epoch',type=int, default=0, help="evaluate the dev set after this number of epoch")

    parser.add_argument("--save_param",type=int, choices=[0,1] ,default=0)

    args = parser.parse_args()
    for k in args.__dict__:
        print(k + ": " + str(args.__dict__[k]))
    return args


def get_optimizer(config: Config, model: nn.Module):
    params = model.parameters()
    if config.optimizer.lower() == "sgd":
        return optim.SGD(params, lr=config.learning_rate, weight_decay=float(config.l2))
    elif config.optimizer.lower() == "adam":
        return optim.Adam(params)
    else:
        print("Illegal optimizer: {}".format(config.optimizer))
        exit(1)

def batching_list_instances(config: Config, insts:List[Instance]):
    train_num = len(insts)
    batch_size = config.batch_size
    total_batch = train_num // batch_size + 1 if train_num % batch_size != 0 else train_num // batch_size
    batched_data = []
    for batch_id in range(total_batch):
        one_batch_insts = insts[batch_id * batch_size:(batch_id + 1) * batch_size]
        batched_data.append(simple_batching(config, one_batch_insts))

    return batched_data

def learn_from_insts(config:Config, epoch: int, train_insts, dev_insts, test_insts):
    # train_insts: List[Instance], dev_insts: List[Instance], test_insts: List[Instance], batch_size: int = 1
    model = NNCRF(config)
    optimizer = get_optimizer(config, model)
    train_num = len(train_insts)
    print("number of instances: %d" % (train_num))
    print(colored("[Shuffled] Shuffle the training instance ids"))
    random.shuffle(train_insts)



    batched_data = batching_list_instances(config, train_insts)
    dev_batches = batching_list_instances(config, dev_insts)
    test_batches = batching_list_instances(config, test_insts)

    best_dev = [-1, 0]
    best_test = [-1, 0]

    model_name = "models/lstm_{}_{}_crf_{}_{}_head_{}_elmo_{}.m".format(config.hidden_dim, config.second_hidden_size, config.dataset, config.train_num, config.use_head, config.use_elmo)
    res_name = "results/lstm_{}_{}_crf_{}_{}_head_{}_elmo_{}.results".format(config.hidden_dim, config.second_hidden_size, config.dataset, config.train_num, config.use_head, config.use_elmo)
    print("[Info] The model will be saved to: %s, please ensure models folder exist" % (model_name))

    for i in range(1, epoch + 1):
        epoch_loss = 0
        start_time = time.time()
        model.zero_grad()
        if config.optimizer.lower() == "sgd":
            optimizer = lr_decay(config, optimizer, i)
        for index in np.random.permutation(len(batched_data)):
        # for index in range(len(batched_data)):
            model.train()
            batch_word, batch_wordlen, batch_char, batch_charlen, adj_matrixs, batch_label = batched_data[index]
            loss = model.neg_log_obj(batch_word, batch_wordlen,batch_char, batch_charlen, batch_label)
            epoch_loss += loss.item()
            loss.backward()
            # # torch.nn.utils.clip_grad_norm_(model.parameters(), config.clip) ##clipping the gradient
            optimizer.step()
            model.zero_grad()

        end_time = time.time()
        print("Epoch %d: %.5f, Time is %.2fs" % (i, epoch_loss, end_time - start_time), flush=True)

        if i + 1 >= config.eval_epoch:
            model.eval()
            dev_metrics = evaluate(config, model, dev_batches, "dev")
            test_metrics = evaluate(config, model, test_batches, "test")
            if dev_metrics[2] > best_dev[0]:
                print("saving the best model...")
                best_dev[0] = dev_metrics[2]
                best_dev[1] = i
                best_test[0] = test_metrics[2]
                best_test[1] = i
                torch.save(model.state_dict(), model_name)
            model.zero_grad()

    print("The best dev: %.2f" % (best_dev[0]))
    print("The corresponding test: %.2f" % (best_test[0]))
    # model.load_state_dict(torch.load(model_name))
    model.eval()
    evaluate(config, model, test_batches, "test")



def evaluate(config:Config, model: NNCRF, batch_insts_ids, name:str):
    ## evaluation
    metrics = np.asarray([0, 0, 0], dtype=int)
    for batch in batch_insts_ids:
        batch_max_scores, batch_max_ids = model.decode(batch)
        metrics += eval.evaluate_num(batch_max_ids, batch[-1], batch[1], config.idx2labels)
    p, total_predict, total_entity = metrics[0], metrics[1], metrics[2]
    precision = p * 1.0 / total_predict * 100 if total_predict != 0 else 0
    recall = p * 1.0 / total_entity * 100 if total_entity != 0 else 0
    fscore = 2.0 * precision * recall / (precision + recall) if precision != 0 or recall != 0 else 0
    print("[%s set] Precision: %.2f, Recall: %.2f, F1: %.2f" % (name, precision, recall,fscore), flush=True)
    return [precision, recall, fscore]


def test(config: Config, test_insts_ids, batch_size):
    model_name = "models/lstm_{}_{}_crf_{}_{}_head_{}_elmo_{}.m".format(config.hidden_dim, config.second_hidden_size, config.dataset, config.train_num, config.use_head, config.use_elmo)
    res_name = "results/lstm_{}_{}_crf_{}_{}_head_{}_elmo_{}.results".format(config.hidden_dim, config.second_hidden_size, config.dataset, config.train_num, config.use_head, config.use_elmo)
    model = NNCRF(config)
    model.load_state_dict(torch.load(model_name))
    model.eval()
    test_batches = batching_instances(config, test_insts_ids, batch_size)
    evaluate(config, model, test_batches, "test")
    # write_results(res_name, test_insts)

def write_results(filename:str, insts):
    f = open(filename, 'w', encoding='utf-8')
    for inst in insts:
        for i in range(len(inst.input)):
            words = inst.input.words
            tags = inst.input.pos_tags
            heads = inst.input.heads
            dep_labels = inst.input.dep_labels
            output = inst.output
            prediction = inst.prediction
            f.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format(i, words[i], tags[i], heads[i], dep_labels[i], output[i], prediction[i]))
        f.write("\n")
    f.close()



if __name__ == "__main__":



    parser = argparse.ArgumentParser(description="LSTM CRF implementation")
    opt = parse_arguments(parser)
    conf = Config(opt)

    reader = Reader(conf.digit2zero)
    setSeed(opt, conf.seed)

    # trains = reader.read_conll(conf.train_file, conf.train_num, True)
    # devs = reader.read_conll(conf.dev_file, conf.dev_num, False)
    # tests = reader.read_conll(conf.test_file, conf.test_num, False)
    trains = reader.read_txt(conf.train_file, conf.train_num, True)
    devs = reader.read_txt(conf.dev_file, conf.dev_num, False)
    tests = reader.read_txt(conf.test_file, conf.test_num, False)
    # print(trains[-1].input.words)

    if conf.use_elmo:
        print('Loading the elmo vectors for all datasets.')
        reader.load_elmo_vec(conf.train_file + ".elmo.vec", trains)
        reader.load_elmo_vec(conf.dev_file + ".elmo.vec", devs)
        reader.load_elmo_vec(conf.test_file + ".elmo.vec", tests)

    conf.use_iobes(trains)
    conf.use_iobes(devs)
    conf.use_iobes(tests)
    conf.build_label_idx(trains)

    # conf.build_deplabel_idx(trains)
    # conf.build_deplabel_idx(devs)
    # conf.build_deplabel_idx(tests)
    # print("# deplabels: ", conf.deplabels)
    # print("dep label 2idx: ", conf.deplabel2idx)

    conf.build_word_idx(trains, tests, devs)
    conf.build_emb_table()

    conf.find_singleton(trains)
    ids_train = conf.map_insts_ids(trains)
    ids_dev = conf.map_insts_ids(devs)
    ids_test= conf.map_insts_ids(tests)


    print("num chars: " + str(conf.num_char))
    # print(str(config.char2idx))

    print("num words: " + str(len(conf.word2idx)))
    # print(config.word2idx)
    if opt.mode == "train":
        learn_from_insts(conf, conf.num_epochs, trains, devs, tests)
    else:
        ## Load the trained model.
        test(conf, ids_test, conf.batch_size)
        # pass

    print(opt.mode)