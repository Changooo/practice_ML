import torch 
import torch.nn as nn
import torch.optim as optim
import numpy as np
import pandas as pd
from torch.utils.data import TensorDataset 
from torch.utils.data import DataLoader 
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import StandardScaler
device = torch.device("cuda")


class util:
    def fix_random_seed():
        torch.manual_seed(0)
        torch.cuda.manual_seed(0)
        torch.cuda.manual_seed_all(0)
        np.random.seed(0)

    def load_dataset():
        # 저수위	방수로	저수량	저수율	유입량	공용량	총 방류량	발전	여수로	기타	취수량
        # ["level", "1", "contain", "2", "income", "3", "outcome", "4", "5", "6", "7"]

        # paldang loading
        paldang_level = pd.read_csv("./dataset/paldang_level.csv")
        paldang_level.columns = ["datetime", "paldang_level", "1", "paldang_contain", "2", "paldang_income", "3", "paldang_outcome", "4", "5", "6", "7"]
        paldang_level = paldang_level.drop(columns=['1', '2', '3', '4', '5', '6', '7'])
        paldang_level['datetime'] = paldang_level['datetime'].str.slice(start=0, stop=-1)

        # jamsoo loading
        jamsoo_level = pd.read_csv("./dataset/jamsoo_level.csv")
        js = []
        for i in range(len(jamsoo_level)):
            oneday = None
            date = ""
            for index, j in enumerate(jamsoo_level.loc[i]):
                datetime = ""
                if index==0:
                    date = j
                else:
                    time = str(index)
                    datetime = date + " " + (time if len(time)>1 else "0"+time)
                    oneday = [datetime, j]     
                    js.append(oneday)
        jamsoo_level = pd.DataFrame(js, columns=["datetime", "jamsoo_level"])

        # songjeong loading
        songjeong_rain = pd.read_csv("./dataset/songjeong_rain.csv")
        sj = []
        for i in range(len(songjeong_rain)):
            oneday = None
            date = ""
            for index, j in enumerate(songjeong_rain.loc[i]):
                datetime = ""
                if index==0:
                    date = str(int(j))
                    date = date[:4]+'-'+date[4:6]+'-'+date[6:]
                else:
                    time = str(index)
                    datetime = date + " " + (time if len(time)>1 else "0"+time)
                    oneday = [datetime, j]     
                    sj.append(oneday)
        songjeong_rain = pd.DataFrame(sj, columns=["datetime", "songjeong_rain"])

        # outer join (record should be 3134days * 24hours = 75216)
        temp = pd.merge(paldang_level, jamsoo_level, left_on='datetime', right_on='datetime', how='right')
        dataset = pd.merge(songjeong_rain, temp, left_on='datetime', right_on='datetime', how='right')
        
        return dataset

    def preprocessing(data, window_size, output_size):
        x, y = data
        x_data = []
        y_data = []
        for index in range(len(y)):
            if index+window_size+output_size > len(y):
                break
            x_data.append(x[index:index+window_size])
            y_data.append(y[index+window_size:index+window_size+output_size])
        
        return torch.FloatTensor(x_data), torch.FloatTensor(y_data)

    def split_train_and_test(dataset, percentage):
        x, y = dataset
        split = int(len(x)*percentage)
        x_train = x[:split]
        y_train = y[:split]
        x_test = x[split:]
        y_test = y[split:]
        return (x_train, y_train), (x_test, y_test)

class simpleMLP:
    def __init__(self, input_size, output_size):
        self.W = torch.FloatTensor(np.random.rand(input_size, output_size)).to(device)
        self.b = torch.FloatTensor(np.random.rand(output_size)).to(device)
        self.W.requires_grad_(True)
        self.b.requires_grad_(True)
        
    def forward(self, x):
        return x.matmul(self.W)+self.b    
    
    def parameters(self):
        return [self.W, self.b]
    
class simpleRNN:
    def __init__(self, input_size, hidden_size):
        self.layer = len(hidden_size)
        self.cell = []
        self.params = []
        self.status = []
        self.output = None
        self.tanh = nn.Tanh()
        for l in range(self.layer):
            cell = simpleMLP(input_size if l==0 else hidden_size[l-1], hidden_size[l])
            Wh = torch.FloatTensor(np.random.rand(hidden_size[l], hidden_size[l])).to(device)
            bh = torch.FloatTensor(np.random.rand(hidden_size[l])).to(device)
            self.params.append([Wh, bh])
            self.cell.append(cell)
            self.status.append(None)            
    
    def forward(self, x):
        for t in range(x.shape[-2]):
            for l in range(self.layer):
                status = self.cell[l].forward(x[..., t:t+1, :] if l==0 else self.status[l-1]) + ((self.status[l].matmul(self.params[l][0])+self.params[l][1]) if t!=0 else 0)
                self.status[l] = self.tanh(status)
            self.output = torch.cat([self.output, self.status[l]], dim=-2) if t!=0 else self.status[l]
        return self.output
    
    def parameters(self):
        p = []
        for mlp in self.cell:
            for pa in mlp.parameters():
                p.append(pa)
        for h in self.params:
            for hnb in h:
                p.append(hnb)
        return p
    
class myRNN:
    def __init__(self, input_size, hidden_size, output_size, output_length, window_size, learning_rate, train_size, batch_size, epoch):
        util.fix_random_seed()
        self.output_length = output_length
        self.rnn = simpleRNN(input_size, hidden_size)
        self.mlp = simpleMLP(hidden_size[-1], output_size)
        self.input_size = input_size
        self.output_size = output_size
        self.window_size = window_size
        self.output_length = output_length
        self.hidden_size = hidden_size
        self.learning_rate = learning_rate
        self.train_size = train_size
        self.batch_size = batch_size
        self.epoch = epoch
    
    def forward(self, x):
        rnn_output = self.rnn.forward(x)
        rnn_output = rnn_output[..., -self.output_length:, :]
        return self.mlp.forward(rnn_output)
    
    def parameters(self):
        return [*self.rnn.parameters(), *self.mlp.parameters()]
    
    def cost_function(self):
        def cost_function (prediction, Y, a):
            err = prediction-Y
            cost = err**2
            cost[err<0] *= a
            cost[err>0] /= a
            cost = cost.mean()
            return cost
        return cost_function
    
    def safe_function(self):
        def safe_function (prediction, Y):
            # err X, safety O 
            err = prediction-Y
            cost = err**2
            cost[err>0] *= 0
            cost = cost.mean()
            return cost
        return safe_function

    def train(self, train_data, hp):
        print("["+str(round(hp, 1))+", ", end="")
        
        # create minibatch
        x_train, y_train = train_data
        dataset = TensorDataset(x_train, y_train)
        dataloader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        # model set
        optimizer = optim.Adam(self.parameters(), self.learning_rate)
        # MSE_function = nn.MSELoss()
        cost_function = self.cost_function()
        # safe_function = myrnn.safe_function()

        # train data
        for epo in range(self.epoch):
            for index, minibatch in enumerate(dataloader):
                # droplast
                if index == len(dataloader)-1:
                    break
                X = minibatch[0].to(device)
                Y = minibatch[1].to(device)
                prediction = self.forward(X).to(device)
                cost = cost_function(prediction, Y, hp)
            
                optimizer.zero_grad()
                cost.backward()
                optimizer.step()
            # if epo%10 == 0:
            #     print(cost)
            #     pass
            
    def test(self, test_data, hp):
        # test data
        x_test, y_test = test_data
        dataset = TensorDataset(x_test, y_test)
        dataloader = DataLoader(dataset, batch_size=1, shuffle=False)
        MSE_function = nn.MSELoss()
        cost_function = self.cost_function()
        safe_function = self.safe_function()

        predict = []
        real = []

        for index, minibatch in enumerate(dataloader):
            X = minibatch[0].to(device)
            Y = minibatch[1]
            prediction = self.forward(X).cpu()
            predict.append(prediction.squeeze(-1).squeeze(0).detach().numpy()[-1])
            real.append(Y.squeeze(-1).squeeze(0).numpy()[-1])

        frame = np.zeros((len(real), 5))
        predict = np.array(predict).reshape(-1, 1)
        real    = np.array(real   ).reshape(-1, 1)
        predict = np.concatenate((frame, predict), axis=1)
        real    = np.concatenate((frame, real   ), axis=1)

        predict = minMaxScaler.inverse_transform(predict)[:, 5:6]
        real    = minMaxScaler.inverse_transform(real   )[:, 5:6]
        predict = np.round(predict, 3)
        real    = np.round(real   , 3)


        print(MSE_function(torch.FloatTensor(predict), torch.FloatTensor(real)).numpy(), end=", ")
        print(cost_function(torch.FloatTensor(predict), torch.FloatTensor(real), hp).numpy(), end=", ")
        print(safe_function(torch.FloatTensor(predict), torch.FloatTensor(real)).numpy(), end="], ")
        print("")


###################################################################################
################################START##############################################
###################################################################################


# features
input_size = 6
output_size = 1

# hyper parameters
window_size = 10
output_length = 1
hidden_size = [5, 3]
learning_rate = 0.001
train_size = 0.9
batch_size = 300
epoch = 120


###################################################################################
################################START##############################################
###################################################################################


# load dataset
dataset = util.load_dataset()

# check missing value
# print(dataset.isnull().sum())

# fill missing value
dataset = dataset.fillna(method='ffill')

# drop datetime
dataset = dataset.drop(columns=['datetime'])

# scaling data
minMaxScaler = MinMaxScaler(feature_range=(0,10))
dataset = minMaxScaler.fit_transform(dataset)
dataset = pd.DataFrame(dataset)

# split x & y
x_dataset = dataset
y_dataset = dataset[[5]].copy()

# split train & test 
train, test = util.split_train_and_test((x_dataset, y_dataset), train_size)
x_train, y_train = train
x_test, y_test = test

# split window & convert to tensor
train_data = util.preprocessing((x_train.to_numpy().tolist(), y_train.to_numpy().tolist()), window_size, output_length)   
test_data = util.preprocessing((x_test.to_numpy().tolist(), y_test.to_numpy().tolist()), window_size, output_length)   



hps = np.arange(1.0, 10.0, 0.1)
for hp in hps:
    myrnn = myRNN(input_size, hidden_size, output_size, output_length, window_size, learning_rate, train_size, batch_size, epoch)
    myrnn.train(train_data, hp)
    myrnn.test(test_data, hp)



