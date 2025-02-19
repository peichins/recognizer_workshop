from os import listdir
import math
import random

import pandas as pd
from typing import List
import librosa
from PIL import Image as im
from PIL import ImageFont, ImageDraw

import Spectrogram


class Annot:
    """
    Simple class for annotations
    """
    start: float
    end: float
    ctype: str

    def __init__(self, start, end):
        self.start = start
        self.end = end

    # Check if the given time is inside the interval represented by this annotation
    def time_is_inside(self, val: float):
        if val >= self.start and val <= self.end:
            return True
        else:
            return False
        
    
def normalize_map_key_names(params):
    """
    Modifies the keys of the given map so that they are in a 'normalized' form.

    This is useful when reading in values from a config file.
    """
    resultMap = {}
    for k,v in params.items():
        strs = k.split("-")
        newStr = strs[0]
        for s in strs[1:len(strs)]:
            sl = list(s)
            sl[0] = sl[0].upper()
            newStr += ("".join(sl))        
        resultMap[newStr] = v
    return resultMap




def get_count_str(count: int):
    """
    Converts an integer count into a string with the correct number of zeros 
    """
    count_str = "000"
    if count>9:
        count_str = "00"
    if count>99:
        count_str = "0"
    if count>999:
        count_str = ""
    count_str += str(count)
    return count_str


def get_annotations(ann_path: str):
    """
    Loads a Raven annoytations file and stores it as a list of .
    Need to be careful to not duplicate rows - 1 for waveform and 1 for spectrogram.
    """

    # Read annotation file
    df = pd.read_csv(ann_path, delimiter='\t' )
    
    # Set of selection numbers
    selnums = set()

    # Get annotations
    anns: List[Annot] = []

    step = 1
    
    for i in range(0,df.shape[0], step):
        # Make sure that we don't include annotation more than once
        selnum = df.iloc[i]['Selection']
        if selnum in selnums:
            continue
        selnums.add(selnum)
        start_time = df.iloc[i]['Begin Time (s)']
        end_time = df.iloc[i]['End Time (s)']    
        a = Annot(start_time, end_time)
        if 'Call Type' in df.columns:
            a.ctype = df.iloc[i]['Call Type']
        else:
            a.ctype = ""
        if 'Label' in df.columns:
            a.ctype = df.iloc[i]['Label']
        anns.append(a)
    
    return anns


def find_filenames( path_to_dir, suffix=".csv" ):
    """
    Retrieve list of files with given extension
    """
    filenames = listdir(path_to_dir)
    return [ filename for filename in filenames if filename.endswith( suffix ) ]


def get_wav_length(fpath):
    """
    Gets the length of a wav file using librosa
    """
    samples, sample_rate = librosa.core.load(fpath)
    duration = len(samples)/sample_rate
    return duration


def matching_annotation_file(dir, wfile):
    """
    Check if wav file has a matching annotation file by matching the prefix 
    """
        
    prefix = wfile[0:-4]
    files = find_filenames( dir, suffix=".txt" )    
    for f in files:
         if f.startswith(prefix):
             return f

    return ""   


def write_raven_anns(anns: List[Annot], file_path):
    """
    Write a Raven annotation file with a given set of column headers
    """
    
    header = "Selection\tView\tChannel\tBegin Time (s)\tEnd Time (s)\tLow Freq (Hz)\tHigh Freq (Hz)\tDelta Time (s)\tDelta Freq (Hz)\tPeak Amp (U)\tSpecies"

    with open(file_path, 'w') as f:
        f.write(header+"\n")
        for idx, ann in enumerate(anns):
            dtime = ann.end - ann.start
            astr = str(ann.start)+"\t"+str(ann.end)+"\t500.00\t7000.00\t"+str(dtime)+"\t6500.00\t0\t" + ann.ctype + "\n"
            f.write(""+str(idx+1)+"\tSpectrogram 1\t1\t"+astr)
            

def makeSpecFromWav(wav_file_path, spec_image_path, fftWinSize, fftOverlap, maxFreq, timeWin):
    
    '''
    Processes a single wav file.
    Generates spectrogram for entire wav file and adds to the spec directory.
    '''    

    data, sample_rate = librosa.core.load( wav_file_path, sr=None )
    duration = len(data)/sample_rate

    spec = Spectrogram.Spectrogram(data, sample_rate, duration)
    spec.make_spec( fftWinSize, fftOverlap, maxFreq, timeWin)
    img = spec.get_image()
    img.save( spec_image_path )
    
     
    
def balance_dataset(df):
    '''
    oversamples from the poorer class so that the number of rows is the same per class
    '''

    print(f'balancing dataset of {df.shape[0]} rows')

    counts = df['label'].value_counts()
    target_num = max(counts)
    new_indexes = []
    random.seed(4321)

    for label in counts.index:

        cur_label_indexes = list(df.index[df['label'] == label])
        # the number times to repeat all the examples
        num_reps = math.floor(target_num / counts[label])
        # the number of random rows to add so that we get exactly the target number
        num_remainder = target_num % counts[label]
        # add these repetitions and randomly selected indexes
        cur_label_new_indexes = (cur_label_indexes * num_reps) + random.sample(cur_label_indexes, num_remainder)
        new_indexes = new_indexes + cur_label_new_indexes

        print(f'number of {label} examples went from {counts[label]} to {len(cur_label_new_indexes)}')

    new_df = df.iloc[new_indexes].reset_index(drop=True)

    return(new_df)


def makeMosaicFromImages(image_list):
    
    '''
    Makes a (3 x n) mosaic image from a list of image patches of size 256 x 128.    
    '''    

    num_images = len(image_list)

    margin = 30
    images_vert = int(num_images / 3)
    h = images_vert * 128 + (images_vert-1) * margin + margin
    w = 3 * 256 + 2 * margin

    font = ImageFont.truetype('ayar.ttf', 16) 
    new_image = im.new( "L", (w, h))
    draw = ImageDraw.Draw(new_image) 

    for i in range(0, num_images):
        y = int(i / 3) * (128 + margin) + margin
        x = (i % 3) * (256 + margin)
        new_image.paste(image_list[i][1], (x, y))

        draw.text( (x+120, y-25), str(image_list[i][0]), fill ="white", font = font, align ="left") 

    new_image.save('incorrect.png')







