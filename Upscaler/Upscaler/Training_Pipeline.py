from typing import Dict, Union
from pathlib import Path
from dataclasses import dataclass
from tqdm import tqdm  # For nice progress bar when training the data!
from datetime import date

# Own imports
from Config.Config import PathType, CurrentDevice, TrainingsPath
from NeuralNetworks.NN_Base import NN_Base
from Dataset.Dataset_UE import Dataset_UE, save_exr
from Colorspace.PreProcessing import preprocessing_pipeline, depreprocessing_pipeline
from NeuralNetworks.UNet import Model_UNET
from NeuralNetworks.Model_Custom import Model_Custom
from Utils.Utils import save_model, load_model

# Libs imports
import torch
import torch.nn as nn
import torchvision.transforms.functional as tvf
from torch import optim  # For optimizers like SGD, Adam, etc.
from torch.utils.data import DataLoader  # Gives easier dataset managment by creating mini batches etc.
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.enabled = True


@dataclass()
class ModelHyperparameters:
    in_channels :int = 3
    out_channels :int = 3
    learning_rate :float = 0.001
    batch_size :int = 32
    num_epochs :int = 15


def save_checkpoint(model_save_path:PathType=None,
                    epoch:int=0,
                    model:NN_Base=None, 
                    hyperparams:ModelHyperparameters=None,
                    optimizer:optim=None,
                    dataset_name:str="Dataset_UE"):

        save_model(model_save_path, 
        {
        'epoch': epoch,
        'batch_size': hyperparams.batch_size,
        'lr': hyperparams.learning_rate,
        'Dataset': dataset_name,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        })



def training_pipeline(training:bool=True, model_load:bool=False, device=CurrentDevice, dtype=torch.float32) -> NN_Base:
    
    # Hyperparameters
    hyperparams = ModelHyperparameters()

    # Load Data
    train_ds = Dataset_UE(ds_root_path=Path("E:/MASTERS/UE4/SubwaySequencer_4_26/DumpedBuffers"),
            csv_root_path=Path("E:/MASTERS/UE4/SubwaySequencer_4_26/DumpedBuffers/info_Native.csv"),
            #crop width x height == 128x128 (for now)
            crop_coords=(900, 1028, 500, 628))

    # Create dataloader
    train_loader = DataLoader(dataset=train_ds, batch_size=hyperparams.batch_size, drop_last=True, pin_memory=True)


    # Initialize network
    model = Model_UNET(in_channels=hyperparams.in_channels, out_channels=hyperparams.out_channels).to(device=device, dtype=dtype)

    ## Loss and optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=hyperparams.learning_rate)
    
    if model_load:
        loaded_training_state_dict = load_model(Path("E:/MASTERS/Upscaler/Results/2022-12-11/Trainings/baseline/model_float32_final.pth"))
        model.load_state_dict(loaded_training_state_dict['model_state_dict'])
        optimizer.load_state_dict(loaded_training_state_dict['optimizer_state_dict'])


    if training:
        # Train Network
        avg_loss_per_epoch = []
        model.train() # prep model for training
        for epoch in range(hyperparams.num_epochs):

            #Log pass
            print('Epoch: %03d' % (epoch + 1), end="\n")
            avg_train_loss = 0.0

            if epoch % 5 == 0 or epoch == 1:
                # TODO make better saving pipeline
                model_save_path = Path(TrainingsPath / "model_float32_epoch{}.pth".format(epoch))
                save_checkpoint(model_save_path,
                                epoch,
                                model,
                                hyperparams,
                                optimizer)


            for batch_idx, (data, target) in enumerate(tqdm(train_loader)):

                #Zero gradients
                optimizer.zero_grad()

                # Get data to cuda if possible
                data = data.to(device=device, dtype=dtype)
                target = target.to(device=device, dtype=dtype)

                # PreProcess the data
                data = preprocessing_pipeline(data)
                target = preprocessing_pipeline(target)

                # forward
                pred = model(data)
                loss = criterion(pred, target)

                # accumulate loss, loss * amount N batch size
                avg_train_loss += loss.item() * data.size(0)

                # loss backward and optimizer
                loss.backward()
                optimizer.step()

            # divide avg train loss by length of data loader sampler
            # it will give a correct avg loss
            # if divided by batch_size, then sometimes it may be not correct,
            # because batch_size is sometimes not dividable by num of samples
            avg_train_loss = avg_train_loss / len(train_loader.sampler)
            avg_loss_per_epoch.append(avg_train_loss)

            #Log pass
            print(' Avg loss: %.3f' % avg_train_loss, end="\n")


        import matplotlib.pyplot as plt
        # summarize history for loss after training
        fig, axs = plt.subplots(figsize = (20,6))
        plt.plot(avg_loss_per_epoch)
        plt.title('model loss')
        plt.ylabel('loss')
        plt.xlabel('epoch')
        plt.legend(['train', 'test'], loc='upper left')
        plt.show()


        model_save_path = Path(TrainingsPath / "model_float32_final.pth")
        save_checkpoint(model_save_path,
                        epoch,
                        model,
                        hyperparams,
                        optimizer)

    return model