
import os
import torch
import torch.nn.functional as F
import torch.optim as optim
from torchvision import transforms
from datetime import datetime
import NeuralNets
import RavenBinaryDataset
import utils
import config
from pathlib import Path


torch.backends.cudnn.enabled = False
torch.manual_seed(3)


train_losses = []
train_counter = []
test_losses = []
test_counter = []


def test_network(net, test_loader, log):
    """
    Loop over test set and accumulate statistics of correct predictions
    """

    # Make sure that the network is in eval mode
    net.eval()

    test_loss = 0
    correct_count = 0
    
    item_count = 0
    correct_items = list(range(0,len(test_loader.dataset)))
    pred_items = list(range(0,len(test_loader.dataset)))

    targets = []

    with torch.no_grad():
   
        for data, target in test_loader:
            # Probably don't need to shift data to device
            #data, target = data.to(device), target.to(device)
            output = net(data)
            test_loss += F.nll_loss(output, target, reduction='sum').item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            
            # Record the number of correct predictions
            corr = pred.eq(target.view_as(pred))

            # Record the predictions 
            for i, x in enumerate(pred):

                idx = item_count + i
                pred_items[idx] = x.item()

            # Record the correct items 
            for i, x in enumerate(corr):
                idx = item_count + i
                if x:
                    correct_items[idx] = 1
                else:
                    correct_items[idx] = 0

            item_count += len(corr)        
            
            correct_count += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)

    message_str = '\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct_count, len(test_loader.dataset),
        100. * correct_count / len(test_loader.dataset))

    print(message_str)

    item_list = test_loader.dataset.get_item_list()

    # Write dataset
    log.write( "\nTEST SET\n")    
    for i, item in enumerate(item_list):        
        log_message = str(item_list[i][1]) + ", " + str(pred_items[i]) + ", " + str(item_list[i][4]) + ",  " + str(item_list[i][2]) + ",  " + str(item_list[i][3])
        log.write( log_message + "\n")

    # Write evaluation message to log file    
    log.write("\n" + message_str)

    log.write( "\nCORRECT " +  str(correct_count) + "\n\n")

    # Write out incorrect results to log file
    image_list = []
    log.write( "INCORRECT " +  str(len(test_loader.dataset) - correct_count) + "\n\n")
    for i, item in enumerate(item_list):        
        if correct_items[i] == 0:
            log_message = "" + str(item_list[i][0]) + "  Class: " + str(item_list[i][1]) + "  Time: " + str(item_list[i][2])
            log_message += ("  " + str(item_list[i][3]) )              
            log.write( log_message + "\n")
            image_list.append((item[0], item[4]))

    # Save incorrect images
    # utils.makeMosaicFromImages(image_list)
    
    
def train_network(epoch, net, optim, train_loader, trainedModelPath, log):
    '''
    Train the netowrk with the data from train_loader
    '''
    
    log.write("\n\n---------------")
    log.write("\nEPOCH   " + str(epoch))
    log.write("\n---------------\n\n")

    # Make sure that we are in train mode
    net.train()

    # Interval for reporting to the screen
    report_interval = 5

    item_count = 0
    correct_items = list(range(0,len(train_loader.dataset)))
    pred_items = list(range(0,len(train_loader.dataset)))

    # Loop over batches of training data
    for batch_idx, (data, target) in enumerate(train_loader):
        optim.zero_grad()
        output = net(data)

        loss = F.nll_loss(output, target)
        loss.backward()
        optim.step()

        pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
        
        # Record the number of correct predictions
        corr = pred.eq(target.view_as(pred))

        # Record the predictions 
        for i, x in enumerate(pred):
            idx = item_count + i
            pred_items[idx] = x.item()

        # Record the correct items 
        for i, x in enumerate(corr):
            idx = item_count + i
            if x:
                correct_items[idx] = 1
            else:
                correct_items[idx] = 0

        item_count += len(corr)    


        if batch_idx % report_interval == 0:

            message_str = 'Train Epoch: {} [{}/{}]\tLoss: {:.6f}'.format(
            epoch, batch_idx * len(data), len(train_loader.dataset), loss.item())

            print(message_str)        
            log.write(message_str+"\n")
            log.flush()

            train_losses.append( loss.item() )
            train_counter.append( (batch_idx*32) + ((epoch-1)*len(train_loader.dataset)) )


    # Write dataset
    item_list = train_loader.dataset.get_item_list()
    log.write( "\nTRAIN SET\n")    
    for i, item in enumerate(item_list):        
        log_message = str(item_list[i][1]) + ", " + str(pred_items[i]) + ", " + str(item_list[i][4]) + ",  " + str(item_list[i][2]) + ", " + str(item_list[i][3])
        log.write( log_message + "\n")


    # Save the model at the end of each training epoch
    models_dir = os.path.dirname(trainedModelPath)
    if not os.path.exists(models_dir):
        os.makedirs(models_dir, exist_ok=True)

    # Save the model at the end of each training epoch    
    torch.save(net.state_dict(), trainedModelPath)



def train(train_params, spec_params):
    """
    Enty point for training the neural network.

    """
    
    print("\n\nTraining ...")

    # First check for valid parameter values
    if train_params["trainedModel"] == "":
        print("ERROR: Please provide a valid path for the trained model.")
        return False       

    if train_params["testSetSize"] < train_params["batchSize"]:
        print("ERROR: The test set size is less than the batch size.\n")
        print("Change the test set size and/or batch size so that the test set size is equal to or greater than the batch size.") 
        return

    # Make sure that the training directory exists. The training directory is the parent directory of the log file.
    log_dir = os.path.dirname(train_params["log"])
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Start the log file with parameter values
    log = open( train_params["log"], 'w')
    log.write( "\n-----------\nParameters\n-----------\n\n" )
    log.write( config.params_to_string(spec_params) )
    log.write( "\n\n" )
    log.write( config.params_to_string(train_params) )
    log.write( "\n\n" )    
    log.write( "\n-----------\nTraining\n-----------\n" )

    # Write the current time to the log file
    now = datetime.now()    
    log.write( "\nTime:  " + now.strftime("%H:%M:%S") + "\n\n")


    # This map defines the number of times to duplicate data for the train and test sets
    class_repetitions = {}
    class_repetitions["pos"] = 1
    class_repetitions["neg"] = 1
 
    # This is our standard transform
    # This should become a parameter in future
    transform = transforms.Compose([                   
        transforms.ToTensor(),
        transforms.Normalize([0.3], [0.3])             
    ])

    # Get the train and test datasets
    new_filename = os.path.splitext(train_params["dataCSV"])[0] + "_balanced.csv"

    ds_train, ds_test = RavenBinaryDataset.MakeRavenBinaryDatasetSplit( train_params["dataCSV"], new_filename, train_params["randomSeed"], 
        train_params["testSetSize"], spec_params, class_repetitions, transform = transform )


    # Check for badly formed datasets
    if ds_train == None or ds_test == None:
        return

    # Make the data loaders
    loader_train = torch.utils.data.DataLoader( ds_train, int(train_params["batchSize"]), shuffle=True)
    loader_test = torch.utils.data.DataLoader( ds_test, int(train_params["batchSize"]), shuffle=True)

    print("\nNumber of training data items: " + str(len(loader_train) * int(train_params["batchSize"]))) 
    print("Number of testing data items: " + str(len(loader_test) * int(train_params["batchSize"]))) 
    print("\n")

    network = None
    
    # Load the neural network model if we are using a pre-trained base model
    if not train_params["baseModel"] == "":
        network = NeuralNets.CNN_4_Layers(512, 112, 12, 24, 32, 48)
        network_state_dict = torch.load( train_params["baseModel"] )
        network.load_state_dict(network_state_dict)
        
        # Replace the last 2 layers
        network.fc1 = torch.nn.Linear( 48 * 4 * 12, 512)    
        network.fc2 = torch.nn.Linear( 512, 2)
    
        network.num_classes = 2
    # Use neural network without pre-trained model    
    else:
        network = NeuralNets.CNN_4_Layers(512, 2, 12, 24, 32, 48)
  	
    lr = float(train_params["lr"])    

    # We could expose the momentum parameter as a configuration parameter
    # but don't want to make things too complicated for the moment.
    optimizer = optim.SGD(network.parameters(), lr, momentum=0.9)
    
    # Main training loop
    for epoch in range( int(train_params["epochs"])):
        
        train_network(epoch, network, optimizer, loader_train, train_params["trainedModel"], log)
        test_network(network, loader_test, log)
        








