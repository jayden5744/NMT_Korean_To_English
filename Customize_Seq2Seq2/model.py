import random
import torch
import torch.nn as nn
import torch.nn.functional as F


class StackLSTMCell(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1, bias=True, dropout=0, residual=True):
        super().__init__()
        self.input_size = input_size            # embedding_dim
        self.hidden_size = hidden_size          # rnn_dim
        self.n_layers = n_layers                # n_layers
        self.layers = nn.ModuleList()
        self.residual = residual                # 잔차연결
        self.dropout = nn.Dropout(p=dropout)    # dropout

        for i in range(n_layers):               # LSTM 층 쌓기
            self.layers.append(
                nn.LSTMCell(input_size, hidden_size, bias=bias)
            )
            input_size = hidden_size

    def forward(self, inputs, hidden):
        # input => [batch_size, rnn_dim]
        # hidden => (h_state, c_state)
        # h_state, c_state = [n_layers, batch_size, hidden_size]
        h_state, c_state = hidden  # 이전 hidden, cell 상태 받아오기

        next_h_state, next_c_state = [], []

        for i, layer in enumerate(self.layers):  # 각 층 layer와 idx
            hi = h_state[i]     # => [batch_size, hidden_size]
            ci = c_state[i]     # => [batch_size, hidden_size]

            next_hi, next_ci = layer(inputs, (hi, ci))
            output = next_hi

            if i + 1 < self.n_layers:   # rnn dropout layer
                output = self.dropout(output)

            if self.residual:           # 잔차연결
                inputs = output + inputs
            else:
                inputs = output

            next_h_state.append(next_hi)
            next_c_state.append(next_ci)

        next_hidden = (
            torch.stack(next_h_state, dim=0),   # hidden layer concaternate
            torch.stack(next_c_state, dim=0)    # cell layer concaternate
        )
        # input => [batch_size, rnn_dim]
        # next_hidden => (h_state, c_state)
        # h_state, c_state = [n_layers, batch_size, hidden_size]
        return inputs, next_hidden


class Recurrent(nn.Module):
    def __init__(self, cell, reverse=False):
        super().__init__()
        self.cell = cell
        self.reverse = reverse  # reverse : 양방향 시 사용

    def forward(self, inputs, hidden=None):
        # inputs => [batch_size, sequence_len, embedding_dim]
        # hidden => (h_state, c_state)
        # h_state, c_state = [n_layers, batch_size, hidden_size]
        hidden_size = self.cell.hidden_size
        batch_size = inputs.size()[0]

        if hidden is None:
            n_layers = self.cell.n_layers
            zero = inputs.data.new(1).zero_()
            # hidden 초기화
            h0 = zero.view(1, 1, 1).expand(n_layers, batch_size, hidden_size)
            # Xavier normal 초기화
            nn.init.xavier_normal_(h0)
            # cell 초기화
            c0 = zero.view(1, 1, 1).expand(n_layers, batch_size, hidden_size)
            hidden = (h0, c0)
        outputs = []

        inputs_time = inputs.split(1, dim=1)    # => ([batch_size, 1, embedding_dim] * sequence_len)

        if self.reverse:
            inputs_time = list(inputs_time)
            inputs_time.reverse()

        for input_t in inputs_time:             # sequence_len 만큼 반복
            input_t = input_t.squeeze(1)        # => [batch_size, embedding_dim]
            output_t, hidden = self.cell(input_t, hidden)
            outputs += [output_t]

        if self.reverse:
            outputs.reverse()
        outputs = torch.stack(outputs, dim=1)
        # inputs => [batch_size, sequence_len, embedding_dim]
        # hidden => (h_state, c_state)
        # h_state, c_state = [n_layers, batch_size, hidden_size]
        return outputs, hidden


class BiRecurrent(nn.Module):
    def __init__(self, cell, output_transformer, output_transformer_bias,
                 hidden_transformer, hidden_transformer_bias):
        super().__init__()
        hidden_size = cell.hidden_size * 2
        self.forward_rnn = Recurrent(cell, reverse=False)
        self.reverse_rnn = Recurrent(cell, reverse=True)
        self.output_nn = nn.Linear(hidden_size, output_transformer, bias=output_transformer_bias)
        self.hidden_nn = nn.Linear(hidden_size, hidden_transformer, bias=hidden_transformer_bias)
        self.cell_nn = nn.Linear(hidden_size, hidden_transformer, bias=hidden_transformer_bias)

    def forward(self, inputs, hidden=None):
        forward_output, (forward_hidden, forward_cell) = self.forward_rnn(inputs, hidden)
        reverse_output, (reverse_hidden, reverse_cell) = self.reverse_rnn(inputs, hidden)
        output = torch.cat((forward_output, reverse_output), dim=2)
        output = self.output_nn(output)
        hidden = torch.cat((forward_hidden, reverse_hidden), dim=2)
        hidden = self.hidden_nn(hidden)
        cell = torch.cat((forward_cell, reverse_cell), dim=2)
        cell = self.cell_nn(cell)
        return output, (hidden, cell)


class Encoder(nn.Module):
    def __init__(self, embedding_size, embedding_dim, rnn_dim, rnn_bias, pad_id, n_layers=1, residual_used=True,
                 embedding_dropout=0, rnn_dropout=0, dropout=0, bidirectional=True,
                 encoder_output_transformer=None, encoder_output_transformer_bias=None,
                 encoder_hidden_transformer=None, encoder_hidden_transformer_bias=None):
        super().__init__()
        self.embedding = nn.Embedding(embedding_size, embedding_dim, padding_idx=pad_id)
        self.embedding_dropout = nn.Dropout(p=embedding_dropout)
        self.dropout = nn.Dropout(p=dropout)
        self.bidirectional = bidirectional

        # rnn cell
        cell = StackLSTMCell(input_size=self.embedding.embedding_dim, hidden_size=rnn_dim, n_layers=n_layers,
                             bias=rnn_bias, dropout=rnn_dropout, residual=residual_used)
        if bidirectional:
            assert encoder_output_transformer and encoder_output_transformer_bias \
                   and encoder_hidden_transformer and encoder_hidden_transformer_bias, 'not input transformer parameter'
            # 가정설정문 : parameter 중 하나라도 안들어오면 해당 메세지 출력
            self.rnn = BiRecurrent(cell, encoder_output_transformer, encoder_output_transformer_bias,
                                   encoder_hidden_transformer, encoder_hidden_transformer_bias)
        else:
            self.rnn = Recurrent(cell)

    def forward(self, enc_input):
        # enc_input => [batch_size, sequence_len]
        embedded = self.embedding_dropout(self.embedding(enc_input))
        # embedded => [batch_size, sequence_len, embedding_dim]
        output, (hidden, cell) = self.rnn(embedded)
        output = self.dropout(output)
        # output => [batch_size, sequence_len, rnn_dim]
        # hidden => [n_layer, batch_size, rnn_dim]
        # cell => [n_layer, batch_size, rnn_dim]
        return output, (hidden, cell)


class Decoder(nn.Module):
    def __init__(self, embedding_size, embedding_dim, rnn_dim, rnn_bias, pad_id, n_layers=1, embedding_dropout=0,
                 rnn_dropout=0, dropout=0, residual_used=True):
        super().__init__()
        self.vocab_size = embedding_size
        self.embedding = nn.Embedding(embedding_size, embedding_dim, padding_idx=pad_id)
        self.embedding_dropout = nn.Dropout(p=embedding_dropout)
        self.dropout = nn.Dropout(p=dropout)
        cell = StackLSTMCell(input_size=self.embedding.embedding_dim, hidden_size=rnn_dim, n_layers=n_layers,
                             bias=rnn_bias, residual=residual_used, dropout=rnn_dropout)
        self.rnn = Recurrent(cell)
        self.classifier = nn.Linear(rnn_dim, embedding_size)

    def forward(self, dec_input, hidden):
        embedded = self.embedding_dropout(self.embedding(dec_input))
        output, hidden = self.rnn(inputs=embedded, hidden=hidden)
        # output => [batch_size, sequence_size, rnn_dim]
        output = self.dropout(output)
        # output => [batch_size, sequence_size, rnn_dim]
        output = self.classifier(output)
        # output => [batch_size, sequence_size, embedding_size]
        return output, hidden


class Seq2Seq(nn.Module):
    def __init__(self, encoder, decoder, seq_len, beam_search):
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.seq_len = seq_len
        self.beam_search = beam_search

    def forward(self, enc_input, dec_input, teacher_forcing_rate=0.5):
        # enc_input, dec_input => [batch_size, sequence_len]
        seed_val = 42
        random.seed(seed_val)
        encoder_output, pre_hidden = self.encoder(enc_input)
        # output => [batch_size, sequence_len, rnn_dim]
        # pre_hidden => (hidden, cell)
        # hidden => [n_layer, batch_size, rnn_dim]
        # cell => [n_layer, batch_size, rnn_dim]
        teacher_forcing_rate = 0
        if teacher_forcing_rate == 1.0:  # 교사강요 무조건 적용  => 답을 그대로 다음 input에 넣음
            output, _ = self.decoder(dec_input=dec_input, hidden=pre_hidden)
        else:
            outputs = []
            dec_input_i = dec_input[:, 0].unsqueeze(dim=1)
            for i in range(1, self.seq_len+1):
                output, hidden = self.decoder(dec_input=dec_input_i, hidden=pre_hidden)
                topv, topi = output.topk(1)
                indices = topi.squeeze().detach()
                outputs.append(output)

                if i != self.seq_len:
                    dec_input_i = dec_input[:, i].unsqueeze(dim=1) if random.random() < teacher_forcing_rate \
                        else indices
            output = torch.stack(outputs, dim=1)
        output = F.log_softmax(output, dim=1)
        return output