import argparse
from Customize_Seq2Seq.tools import Trainer, Translation


def get_args():
    parser = argparse.ArgumentParser()
    # 1. File path
    parser.add_argument('--data_path', default='../Data', type=str)
    parser.add_argument('--dictionary_path', default='../Dictionary', type=str)
    parser.add_argument('--src_train_filename', default='train_small.ko', type=str)
    parser.add_argument('--tar_train_filename', default='train_small.en', type=str)
    parser.add_argument('--src_val_filename', default='val_small.ko', type=str)
    parser.add_argument('--tar_val_filename', default='val_small.en', type=str)
    parser.add_argument('--model_path', default='Model', type=str)

    # 2. Model Hyper Parameter
    parser.add_argument('--sequence_size', default=50, type=int)
    parser.add_argument('--embedding_dim', default=500, type=int)

    # 3. Eecoder
    parser.add_argument('--encoder_rnn_dim', default=200, type=int)
    parser.add_argument('--encoder_n_layers', default=3, type=int)

    # 4. Decoder
    parser.add_argument('--decoder_rnn_dim', default=200, type=int)
    parser.add_argument('--decoder_n_layers', default=3, type=int)

    # 5. learning hyper parameter
    parser.add_argument('--learning_method', default='Scheduled_Sampling', type=str,
                        choices=['Teacher_Forcing', 'Scheduled_Sampling', 'Mixed_Sampling'])
    parser.add_argument('--learning_rate', default=0.001, type=float)
    parser.add_argument('--epochs', default=20, type=int)
    parser.add_argument('--batch_size', default=500, type=int)
    parser.add_argument('--plot_count', default=6, type=int)
    parser.add_argument('--train_step_print', default=10, type=int)
    parser.add_argument('--val_step_print', default=100, type=int)
    parser.add_argument('--step_save', default=1000, type=int)
    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()
    Trainer(args)
    #
    # translation = Translation(
    #     checkpoint='Model/126000_model_1.pth',
    #     dictionary_path='../Dictionary',
    #     x_path='../Data/test.ko',
    #     y_path='../Data/test.en'
    # )
    # test = translation.transform('미국의 대통령은 오바마이다')
    # print(test)
