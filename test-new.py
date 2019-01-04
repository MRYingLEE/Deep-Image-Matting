# python test-new.py -i "test/image.png" -b "test/background.png"
import argparse
import math
import os
import random

import cv2 as cv
import keras.backend as K
import numpy as np

#from data_generator import generate_trimap, random_choice
from model import build_encoder_decoder, build_refinement
from utils import compute_mse_loss, compute_sad_loss
from utils import get_final_output, safe_crop, draw_str
from config import batch_size
from config import fg_path, bg_path, a_path
from config import img_cols, img_rows
from config import unknown_code
from utils import safe_crop

################################## The code in this section is digested and modified from original data_generator.py
kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3, 3))

def get_alpha_test(name):
    #fg_i = int(name.split("_")[0])
    #name = fg_files[fg_i]
    #filename = os.path.join('mask', name)
    #alpha = cv.imread(filename, 0)
    alpha = cv.imread(name, 0)
    return alpha

def generate_trimap(alpha):
    fg = np.array(np.equal(alpha, 255).astype(np.float32))
    # fg = cv.erode(fg, kernel, iterations=np.random.randint(1, 3))
    unknown = np.array(np.not_equal(alpha, 0).astype(np.float32))
    unknown = cv.dilate(unknown, kernel, iterations=np.random.randint(1, 20))
    trimap = fg * 255 + (unknown - fg) * 128
    return trimap.astype(np.uint8)

# Randomly crop (image, trimap) pairs centered on pixels in the unknown regions.
def random_choice(trimap, crop_size=(320, 320)):
    crop_height, crop_width = crop_size
    y_indices, x_indices = np.where(trimap == unknown_code)
    num_unknowns = len(y_indices)
    x, y = 0, 0
    if num_unknowns > 0:
        ix = np.random.choice(range(num_unknowns))
        center_x = x_indices[ix]
        center_y = y_indices[ix]
        x = max(0, center_x - int(crop_width / 2))
        y = max(0, center_y - int(crop_height / 2))
    return x, y

################################## The code in this section is digested and modified from original demo.py

def composite4(fg, bg, a, w, h):
    fg = np.array(fg, np.float32)
    bg_h, bg_w = bg.shape[:2]
    x = 0
    if bg_w > w:
        x = np.random.randint(0, bg_w - w)
    y = 0
    if bg_h > h:
        y = np.random.randint(0, bg_h - h)
    bg = np.array(bg[y:y + h, x:x + w], np.float32)
    alpha = np.zeros((h, w, 1), np.float32)
    alpha[:, :, 0] = a / 255.
    im = alpha * fg + (1 - alpha) * bg
    im = im.astype(np.uint8)
    return im, bg

if __name__ == '__main__':
    img_rows, img_cols = 320, 320
    channel = 4

    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--image", help="path to the image file")
    ap.add_argument("-b", "--background", help="path to the background file")
    args = vars(ap.parse_args())
    image_path = args["image"]
    trimap_path = args["background"]

    print(image_path,trimap_path)

    print('Start processing image: {}'.format(image_path))
    pretrained_path = 'models/final.42-0.0398.hdf5'
    #pretrained_path ='https://github.com/foamliu/Deep-Image-Matting/releases/download/v1.0/final.42-0.0398.hdf5'
    encoder_decoder = build_encoder_decoder()
    final = build_refinement(encoder_decoder)
    final.load_weights(pretrained_path)

    #from keras.utils import plot_model
    #plot_model(final, to_file='model.png')

    print(final.summary())

    out_test_path =''# 'merged_test/'
    #test_images = [f for f in os.listdir(out_test_path) if
    #               os.path.isfile(os.path.join(out_test_path, f)) and f.endswith('.png')]
    #samples = random.sample(test_images, 10)
    samples=np.array([image_path])

    bg_test = ''# 'bg_test/'
    #test_bgs = [f for f in os.listdir(bg_test) if
    #            os.path.isfile(os.path.join(bg_test, f)) and f.endswith('.jpg')]
    #sample_bgs = random.sample(test_bgs, 10)
    sample_bgs=np.array([trimap_path])

    total_loss = 0.0
    for i in range(len(samples)):
        filename = samples[i]
        image_name = filename.split('.')[0]

        print('\nStart processing image: {}'.format(filename))

        bgr_img = cv.imread(os.path.join(out_test_path, filename))
        bg_h, bg_w = bgr_img.shape[:2]
        print('bg_h, bg_w: ' + str((bg_h, bg_w)))

        a = get_alpha_test(filename)
        a_h, a_w = a.shape[:2]
        print('a_h, a_w: ' + str((a_h, a_w)))

        alpha = np.zeros((bg_h, bg_w), np.float32)
        alpha[0:a_h, 0:a_w] = a
        trimap = generate_trimap(alpha)
        different_sizes = [(320, 320), (320, 320), (320, 320), (480, 480), (640, 640)]
        crop_size = random.choice(different_sizes)
        x, y = random_choice(trimap, crop_size)
        print('x, y: ' + str((x, y)))

        bgr_img = safe_crop(bgr_img, x, y, crop_size)
        alpha = safe_crop(alpha, x, y, crop_size)
        trimap = safe_crop(trimap, x, y, crop_size)
        cv.imwrite('test/{}_image.png'.format(i), np.array(bgr_img).astype(np.uint8))
        cv.imwrite('test/{}_trimap.png'.format(i), np.array(trimap).astype(np.uint8))
        cv.imwrite('test/{}_alpha.png'.format(i), np.array(alpha).astype(np.uint8))
        print("0")    
        x_test = np.empty((1, img_rows, img_cols, 4), dtype=np.float32)
        x_test[0, :, :, 0:3] = bgr_img / 255.
        x_test[0, :, :, 3] = trimap / 255.

        y_true = np.empty((1, img_rows, img_cols, 2), dtype=np.float32)
        y_true[0, :, :, 0] = alpha / 255.
        y_true[0, :, :, 1] = trimap / 255.

        y_pred = final.predict(x_test)
        print('y_pred.shape: ' + str(y_pred.shape))

        y_pred = np.reshape(y_pred, (img_rows, img_cols))
        print(y_pred.shape)
        
        y_pred = y_pred * 255.0
        y_pred = get_final_output(y_pred, trimap)
        y_pred = y_pred.astype(np.uint8)

        sad_loss = compute_sad_loss(y_pred, alpha, trimap)
        mse_loss = compute_mse_loss(y_pred, alpha, trimap)
        str_msg = 'sad_loss: %.4f, mse_loss: %.4f, crop_size: %s' % (sad_loss, mse_loss, str(crop_size))
        print(str_msg)

        out = y_pred.copy()
        draw_str(out, (10, 20), str_msg)
        cv.imwrite('test/{}_out.png'.format(i), out)
        
        sample_bg = sample_bgs[i]
        bg = cv.imread(os.path.join(bg_test, sample_bg))
        bh, bw = bg.shape[:2]
        wratio = img_cols / bw
        hratio = img_rows / bh
        ratio = wratio if wratio > hratio else hratio
        
        if ratio > 1:
            bg = cv.resize(src=bg, dsize=(math.ceil(bw * ratio), math.ceil(bh * ratio)), interpolation=cv.INTER_CUBIC)
        
        im, bg = composite4(bgr_img, bg, y_pred, img_cols, img_rows)
        cv.imwrite('test/{}_compose.png'.format(i), im)
        cv.imwrite('test/{}_new_bg.png'.format(i), bg)

    K.clear_session()
