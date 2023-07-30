from model.build_model import build_model
import copy
from util.aggregation import personalized_aggregation
import numpy as np
from util.load_data import load_data_with_noisy_label
# from data.dataloader_getter_utils import *
from util.local_training import FedTwinLocalUpdate, globaltest, personalizedtest
import time

from util.get_loss_of_clean_noisy_sample import get_clean_noisy_sample_loss
import torch.nn as nn
from util.loss import CORESLoss
from util.optimizer import f_beta
from metrics import cal_fscore


def FedTwin(args):
    # load dataset
    dataset_train, dataset_test, dict_users, y_train, gamma_s, noisy_sample_idx = load_data_with_noisy_label(args)
    start = time.time()
    # begin training
    netglob = build_model(args)
    # parameter
    m = max(int(args.frac2 * args.num_users), 1)  # num_select_clients
    prob = [1 / args.num_users for i in range(args.num_users)]
    for rnd in range(args.rounds2):
        if rnd <= args.begin_sel:
            print("\rRounds {:d} early training:"
                  .format(rnd), end='\n', flush=True)
        else:
            print("\rRounds {:d} filter noisy data:"
                  .format(rnd), end='\n', flush=True)
        w_locals, p_models, loss_locals, n_bar = [], [], [], []
        idxs_users = np.random.choice(range(args.num_users), m, replace=False, p=prob)
        for idx in idxs_users:  # training over the subset
            local = FedTwinLocalUpdate(args=args, dataset=dataset_train, idxs=dict_users[idx], client_idx=idx)
            p_model, w_local, loss_local, n_bar_k = local.update_weights(net_p=copy.deepcopy(netglob).to(args.device),
                                                                         net_glob=copy.deepcopy(netglob).to(
                                                                             args.device), rounds=rnd)
            w_locals.append(copy.deepcopy(w_local))  # store every updated model
            p_models.append(p_model)
            loss_locals.append(loss_local)
            n_bar.append(n_bar_k)
            # print('\n')
        loss_round = sum(loss_locals) / len(loss_locals)
        w_glob_fl = personalized_aggregation(netglob.state_dict(), w_locals, n_bar, args.gamma)
        netglob.load_state_dict(w_glob_fl)

        # acc_s1 = personalizedtest(args, p_models, dataset_test)
        acc_s2 = globaltest(netglob.to(args.device), dataset_test, args)
        # f_acc.write("third stage round %d, personalized test acc  %.4f \n" % (rnd, acc_s1))
        show_info_loss = "Round %d train loss  %.4f" % (rnd, loss_round)
        show_info_test_acc = "Round %d global test acc  %.4f \n" % (rnd, acc_s2)
        print(show_info_loss)
        print(show_info_test_acc)
        # print("time :", time.time() - start)
        # f_save.write(show_info_loss)
        # f_save.write(show_info_test_acc)
        # f_save.flush()
        if args.without_CR:
            loss_fn = nn.CrossEntropyLoss(reduction='none')
        else:
            loss_fn = CORESLoss(reduction='none')
        Beta = f_beta(rnd * args.local_ep + args.local_ep, args)

        f_scores = []
        all_idxs_users = [i for i in range(args.num_users)]
        if rnd == args.rounds2 - 1:
            for idx in all_idxs_users:
                f_scores.append(cal_fscore(args, loss_fn, Beta, netglob.to(args.device), dataset_train, y_train, dict_users[idx]))
            show_info_Fscore = "Round %d Fscore \n" % (rnd)
            print(show_info_Fscore)
            print(str(f_scores))
        # file_name = "./fscore_" + args.algorithm + ".txt"
        # f = open(file_name, "w")
        # f.writelines(f_scores.to)
        # f.close()

        if rnd == 50 or rnd == (args.rounds2-1):
            # Record the loss for clean and noisy samples separately
            clean_loss_s, noisy_loss_s = get_clean_noisy_sample_loss(
                model=netglob,
                loss_fn=loss_fn,
                dataset=dataset_train,
                noisy_sample_idx=noisy_sample_idx,
                round=rnd,
                beta=Beta
            )
            print(f"{loss_fn.__class__.__name__}:")
            print("clean_loss:")
            print(clean_loss_s)
            print("noisy_loss:")
            print(noisy_loss_s)

    show_time_info = f"time : {time.time() - start}"
    print(show_time_info)
    # f_save.write(show_time_info)
    # f_save.flush()
