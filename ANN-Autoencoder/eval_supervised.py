# import libraries
import os
import sys
import requests
import pandas as pd
import numpy as np
import setGPU
from sklearn.preprocessing import MinMaxScaler
from sklearn.externals import joblib
import seaborn as sns
sns.set(color_codes=True)
import matplotlib.pyplot as plt
#%matplotlib inline
import h5py as h5
from gwpy.timeseries import TimeSeries

from numpy.random import seed
from tensorflow import set_random_seed
import tensorflow as tf


from keras import regularizers
from keras.models import load_model
from tensorflow.keras.losses import mean_absolute_error, MeanAbsoluteError, mean_squared_error, MeanSquaredError
from random import sample as RandSample
import argparse
from sklearn.metrics import roc_curve, auc, accuracy_score

from model import autoencoder_LSTM, autoencoder_Conv, autoencoder_DeepConv

def filters(array, sample_frequency):
    strain = TimeSeries(array, sample_rate=int(sample_frequency))
    white_data = strain.whiten(fftlength=4,fduration=4)
    bp_data = white_data.bandpass(50, 250)
    return(bp_data.value)
    
def main(args):
    outdir = args.outdir
    detector = args.detector
    freq = args.freq
    filtered = args.filtered
    timesteps = int(args.timesteps)
    os.system('mkdir -p %s'%outdir)
    
    load = h5.File('data/default_simulated.hdf','r') 
    
    if int(freq) == 2: 
        freq = 2048
    elif int(freq) == 4: 
        freq = 4096
        
    if freq%2048 != 0: 
        print('WARNING: not a supported sampling frequency for simulated data')
        print('Sampling Frequency: %s'%(freq))
    
    n_noise_events = 5000
    noise_samples = load['noise_samples']['%s_strain'%(str(detector).lower())][:][-n_noise_events:]
    
    if bool(int(filtered)):
        print('filtering data with whitening and bandpass')
        x_noise = [filters(sample, freq) for sample in noise_samples]
        print('Done!')
        
    # Load previous scaler and transform    
    scaler_filename = "%s/scaler_data_%s"%(outdir, detector)
    scaler = joblib.load(scaler_filename) 
    X_train = scaler.transform(x_noise)
    
    # Trim dataset to be batch-friendly
    #x = []
    #for event in range(len(X_train)): 
    #    if X_train[event].shape[0]%timesteps != 0: 
    #        x.append(X_train[event][:-1*int(X_train[event].shape[0]%timesteps)])
    
    # reshape inputs for LSTM [samples, timesteps, features]
    #X_train = np.array(x).reshape(-1, timesteps, 1)
    print("Training data shape:", X_train.shape)
    
    n_injection_events = 5000
    injection_samples = load['injection_samples']['%s_strain'%(str(detector).lower())][:][:n_injection_events]

    if bool(int(filtered)):
        print('filtering data with whitening and bandpass')
        x_injection = [filters(sample, freq) for sample in injection_samples]
        print('Done!')
        
    # Normalize the data
    scaler_filename = "%s/scaler_data_%s"%(outdir, detector)
    scaler = joblib.load(scaler_filename) 
    X_test = scaler.transform(x_injection)
    #X_test = scaler.transform(y.reshape(-1, 1))
    
    #x = []
    #for event in range(len(X_test)): 
    #    if X_test[event].shape[0]%timesteps != 0: 
    #        x.append(X_test[event][:-1*int(X_test[event].shape[0]%timesteps)])
    
    # reshape inputs for LSTM [samples, timesteps, features]
    #X_test = np.array(x).reshape(-1, timesteps, 1)
    print("Testing data shape:", X_test.shape)
    
    directory_list = ['simdata_L1_2KHz_1024Batch_50steps_filtered_LSTM_largesim_mse', 'simdata_L1_2KHz_1024Batch_50steps_filtered_GRU_largesim_mae', 'simdata_L1_2KHz_1024Batch_100steps_filtered_DNN_largesim_mse_run2', 'simdata_L1_2KHz_1024Batch_108steps_filtered_Conv_largesim_mse', 'simdata_L1_2KHz_1024Batch_108steps_filtered_ConvDNN_largesim_mse']
    
    #directory_list = ['simdata_L1_2KHz_1024Batch_100steps_filtered_DNN_largesim_mse_run2', 'simdata_L1_2KHz_1024Batch_108steps_filtered_Conv_largesim_mse', 'simdata_L1_2KHz_1024Batch_108steps_filtered_ConvDNN_largesim_mse']
    
    
    names = ['LSTM Autoencoder', 'GRU Antoencoder', 'DNN Autoencoder', 'CNN Autoencoder', 'CNN-DNN Autoencoder']
    #names = ['DNN Autoencoder', 'CNN Autoencoder', 'CNN-DNN Autoencoder']
    timesteps = [50, 50, 100, 108, 108]
    #timesteps = [100, 108, 108]
    FPR_set = []
    TPR_set = []
    
    for name, directory, timestep in zip(names, directory_list, timesteps): 
        print('Determining performance for: %s'%(name))
        TPR, FPR = TPR_FPR_arrays(X_train, X_test, directory, timestep)
        TPR_set.append(TPR)
        FPR_set.append(FPR)
        print('Done!')
    
    plt.figure()
    lw = 2
    for FPRs, TPRs, name in zip(FPR_set, TPR_set, names):
        plt.plot(FPRs, TPRs,
             lw=lw, label='%s (auc = %0.5f)'%(name, auc(FPRs, TPRs)))
    plt.plot([0, 1], [0, 1], lw=lw, linestyle='--')
    plt.xlim([1e-4, 1])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.xscale('log')
    plt.title('LIGO Unsupervised Autoencoder Anomaly Detection')
    plt.legend(loc="lower right")
    plt.savefig('%s/ROC_curve_log.jpg'%(outdir))

    sys.exit()
    
    times = load['injection_samples']['event_time']
    random_samples = RandSample(range(0, len(injection_samples)), 10)
    
    ### Enable if needed - these are additional plots to check if methods are working ###
    for random_sample in random_samples: 
        event = X_test[random_sample]
        time = times[random_sample] - 1000000000
        
        if event.shape[0]%timesteps != 0: 
            event = event[:-1*int(event.shape[0]%timesteps)]
        event = event.reshape(-1, timesteps, 1)
        
        
        X_pred = model.predict(event)
        
        losses = loss_fn(event, X_pred).eval(session=tf.compat.v1.Session())
        batch_loss = np.mean(losses, axis=1)
        
        fig, ax = plt.subplots(figsize=(14, 6), dpi=80)
        ax.plot(batch_loss)
        plt.axvline(len(batch_loss)*5.5/8, label='actual GW event', color='green')
        plt.axhline(threshold, label='GW event threshold', color='red')
        plt.legend(loc='upper left')
        plt.savefig('%s/batchloss_%s.jpg'%(outdir,time))
        
        
        X_pred_test = np.array(model.predict(event))
        
        fig, ax = plt.subplots(figsize=(14, 6), dpi=80)
        ax.plot(event.reshape(-1)[int(2048*5.5) - 300:int(2048*5.5) + 300], label='truth')
        ax.plot(X_pred_test.reshape(-1)[int(2048*5.5)- 300:int(2048*5.5) + 300], label='predict')
        plt.legend(loc='upper left')
        plt.title('LSTM Autoencoder')
        plt.savefig('%s/middle30ms_%s.jpg'%(outdir,time))
        
        print(X_pred_test.shape)
        X_pred_test = X_pred_test.reshape(X_pred_test.shape[0]*timesteps, X_pred_test.shape[2])
        
        #X_pred_train.index = train.index
        Xtest = event.reshape(event.shape[0]*timesteps, event.shape[2])

        X_pred_test = pd.DataFrame(X_pred_test)
        scored_test = pd.DataFrame()
        scored_test['Loss_mae'] = np.mean(np.abs(X_pred_test-Xtest), axis = 1)
        #scored_test['Threshold'] = threshold
        #scored_test['Anomaly'] = scored_test['Loss_mae'] > scored_test['Threshold']
        #scored_test.plot(logy=True,  figsize=(16,9), ylim=[t/(1e2),threshold*(1e2)], color=['blue','red'])
        scored_test.plot(logy=False,  figsize=(16,9), color=['blue','red'])
        plt.axvline(5.5*2048, label='actual GW event', color='green') #Sampling rate of 2048 Hz with the event occuring 5.5 seconds into sample
        plt.legend(loc='upper left')
        plt.savefig('%s/test_threshold_%s_8sec.jpg'%(outdir, time))
        
    
if __name__ == "__main__":
    """ This is executed when run from the command line """
    parser = argparse.ArgumentParser()
    
    # Required positional arguments
    parser.add_argument("outdir", help="Required output directory")
    parser.add_argument("detector", help="Required output directory")
    parser.add_argument("--freq", help="Sampling frequency of detector in KHz", action='store', dest='freq', default = 4)
    parser.add_argument("--filtered", help="Apply LIGO's bandpass and whitening filters", action='store', dest='filtered', default = 1)
    parser.add_argument("--timesteps", help="Number of timesteps passed to LSTM", action='store', dest='timesteps', default = 100)
    
    args = parser.parse_args()
    main(args)