# Copyright (c) 2019, NVIDIA Corporation. All rights reserved.
#
# This work is made available under the Nvidia Source Code License-NC.
# To view a copy of this license, visit
# https://nvlabs.github.io/stylegan2/license.html

"""Miscellaneous utility functions."""

import os
import pickle
import numpy as np
import PIL.Image
import PIL.ImageFont
import dnnlib
import glob
import re
import tensorflow as tf

#----------------------------------------------------------------------------
# Convenience wrappers for pickle that are able to load data produced by
# older versions of the code, and from external URLs.

def open_file_or_url(file_or_url):
    if dnnlib.util.is_url(file_or_url):
        return dnnlib.util.open_url(file_or_url, cache_dir='.stylegan2-cache')
    return open(file_or_url, 'rb')

def load_pkl(file_or_url):
    with open_file_or_url(file_or_url) as file:
        return pickle.load(file, encoding='latin1')

def locate_latest_pkl(result_dir):
    allpickles = sorted(glob.glob(os.path.join(result_dir, '0*', 'network-*.pkl')))
    if len(allpickles) == 0:
        return None, 0.0
    latest_pickle = allpickles[-1]
    resume_run_id = os.path.basename(os.path.dirname(latest_pickle))
    RE_KIMG = re.compile('network-snapshot-(\d+).pkl')
    kimg = int(RE_KIMG.match(os.path.basename(latest_pickle)).group(1))
    return (latest_pickle, float(kimg))

def save_pkl(obj, filename):
    with open(filename, 'wb') as file:
        pickle.dump(obj, file, protocol=pickle.HIGHEST_PROTOCOL)

#----------------------------------------------------------------------------
# Image utils.

def adjust_dynamic_range(data, drange_in, drange_out):
    if drange_in != drange_out:
        scale = (np.float32(drange_out[1]) - np.float32(drange_out[0])) / (np.float32(drange_in[1]) - np.float32(drange_in[0]))
        bias = (np.float32(drange_out[0]) - np.float32(drange_in[0]) * scale)
        data = data * scale + bias
    return data

def create_image_grid(images, grid_size=None):
    assert images.ndim == 3 or images.ndim == 4
    num, img_w, img_h = images.shape[0], images.shape[-1], images.shape[-2]

    if grid_size is not None:
        grid_w, grid_h = tuple(grid_size)
    else:
        grid_w = max(int(np.ceil(np.sqrt(num))), 1)
        grid_h = max((num - 1) // grid_w + 1, 1)

    grid = np.zeros(list(images.shape[1:-2]) + [grid_h * img_h, grid_w * img_w], dtype=images.dtype)
    for idx in range(num):
        x = (idx % grid_w) * img_w
        y = (idx // grid_w) * img_h
        grid[..., y : y + img_h, x : x + img_w] = images[idx]
    return grid

def convert_to_pil_image(image, drange=[0,1]):
    assert image.ndim == 2 or image.ndim == 3
    if image.ndim == 3:
        if image.shape[0] == 1:
            image = image[0] # grayscale CHW => HW
        else:
            image = image.transpose(1, 2, 0) # CHW -> HWC

    image = adjust_dynamic_range(image, drange, [0,255])
    image = np.rint(image).clip(0, 255).astype(np.uint8)
    fmt = 'RGB' if image.ndim == 3 else 'L'
    return PIL.Image.fromarray(image, fmt)

def save_image_grid(images, filename, drange=[0,1], grid_size=None):
    convert_to_pil_image(create_image_grid(images, grid_size), drange).save(filename)

def apply_mirror_augment(minibatch):
    mask = np.random.rand(minibatch.shape[0]) < 0.5
    minibatch = np.array(minibatch)
    minibatch[mask] = minibatch[mask, :, :, ::-1]
    return minibatch

def apply_mirror_augment_v(minibatch):
    mask = np.random.rand(minibatch.shape[0]) < 0.5
    minibatch = np.array(minibatch)
    minibatch[mask] = minibatch[mask, :, ::-1, :]
    return minibatch

def zoom_in(tf_img, alpha=0.1, target_image_shape=None, seed=None):
  """
  Random zoom in to TF image
  Args:
    image: 3-D tensor with a single image.
    alpha: strength of augmentation
    target_image_shape: List/Tuple with target image shape.
  Returns:
    Image tensor with shape `target_image_shape`.
  """

  # Set params
  n = tf.random_uniform(shape=[], minval=1-alpha, maxval=1, dtype=tf.float32, seed=seed, name=None)
  h, w, c = tf_img.shape

  h_t = tf.cast(
    h, dtype=tf.float32, name=None)
  w_t = tf.cast(
    w, dtype=tf.float32, name=None)
  rnd_h = h_t*n
  rnd_w = w_t*n
  if target_image_shape is None:
    target_image_shape = (h, w)

  # Random crop
  crop_size = [rnd_h, rnd_w, 3]
  cropped_img = tf.image.random_crop(
      tf_img,
      crop_size,
      seed=seed,
      name=None
  )

  # resize back to original size
  resized_img = tf.image.resize(
      cropped_img, target_image_shape, method=tf.image.ResizeMethod.BILINEAR, preserve_aspect_ratio=False,
      name=None
  )
  return resized_img


def zoom_out(tf_img, alpha=0.1, target_image_shape=None, seed=None):
  """
  Random zoom out of TF image
  Args:
    img: 3-D tensor with a single image.
    alpha: strength of augmentation
    target_image_shape: List/Tuple with target image shape.
  Returns:
    Image tensor with shape `target_image_shape`.
  """

  # Set params
  n = tf.random_uniform(shape=[], minval=0, maxval=alpha, dtype=tf.float32, seed=seed, name=None)
  h, w, c = tf_img.shape
  if target_image_shape is None:
    target_image_shape = (h, w)

  # Pad image to size (1+2a)*H, (1+2a)*W
  h_t = tf.cast(
    h, dtype=tf.float32, name=None)
  w_t = tf.cast(
    w, dtype=tf.float32, name=None)
  rnd_h = h_t*n
  rnd_w = w_t*n
  paddings = [[rnd_h, rnd_h], [rnd_w, rnd_w], [0, 0]]
  padded_img = tf.pad(tf_img, paddings, 'REFLECT')
  size = ((1+n) * h_t, (1+n) * w_t, c)

  # Random crop to size (1+a)*H, (1+a)*W
  r_cropped_img = tf.image.random_crop(
      padded_img,
      size,
      seed=seed,
      name=None
  )

  # Resize back to original size
  resized_img = tf.image.resize(
      r_cropped_img, (target_image_shape + (c,)), method=tf.image.ResizeMethod.BILINEAR, preserve_aspect_ratio=False,
      name=None
  )
  return resized_img


def X_translate(tf_img, alpha=0.1, target_image_shape=None, seed=None):
    """
    Random X translation within TF image with reflection padding
    Args:
      image: 3-D tensor with a single image.
      alpha: strength of augmentation
      target_image_shape: List/Tuple with target image shape.
    Returns:
      Image tensor with shape `target_image_shape`.
    """
    n = tf.random_uniform(shape=[], minval=0, maxval=alpha, dtype=tf.float32, seed=seed, name=None)

    h, w, c = tf_img.shape
    if target_image_shape is None:
        target_image_shape = (h, w)

    # Pad image to size H, (1+2a)*W
    w_t = tf.cast(
        w, dtype=tf.float32, name=None)
    rnd_w = w_t * n
    paddings = [[0, 0], [rnd_w, rnd_w], [0, 0]]
    padded_img = tf.pad(tf_img, paddings, 'REFLECT')

    # Random crop section at original size
    X_trans = tf.image.random_crop(
        padded_img,
        (target_image_shape + (c,)),
        seed=seed,
        name=None)

    return X_trans


def XY_translate(tf_img, alpha=0.1, target_image_shape=None, seed=None):
  """
  Random XY translation within TF image with reflection padding
  Args:
    image: 3-D tensor with a single image.
    alpha: strength of augmentation
    target_image_shape: List/Tuple with target image shape.
  Returns:
    Image tensor with shape `target_image_shape`.
  """

  n = tf.random_uniform(shape=[], minval=0, maxval=alpha, dtype=tf.float32, seed=seed, name=None)
  h, w, c = tf_img.shape
  if target_image_shape is None:
    target_image_shape = (h, w)

  # Pad image to size (1+2a)*H, (1+2a)*W
  h_t = tf.cast(
    h, dtype=tf.float32, name=None)
  w_t = tf.cast(
    w, dtype=tf.float32, name=None)
  rnd_h = h_t*n
  rnd_w = w_t*n
  paddings = [[rnd_h, rnd_h], [rnd_w, rnd_w], [0, 0]]
  padded_img = tf.pad(tf_img, paddings, 'REFLECT')

  # Random crop section at original size
  XY_trans = tf.image.random_crop(
      padded_img,
      (target_image_shape + (c,)),
      seed=seed,
      name=None
  )
  return XY_trans


def Y_translate(tf_img, alpha=0.1, target_image_shape=None, seed=None):
    """
    Random Y translation within TF image with reflection padding
    Args:
      image: 3-D tensor with a single image.
      alpha: strength of augmentation
      target_image_shape: List/Tuple with target image shape.
    Returns:
      Image tensor with shape `target_image_shape`.
    """
    n = tf.random_uniform(shape=[], minval=0, maxval=alpha, dtype=tf.float32, seed=seed, name=None)

    h, w, c = tf_img.shape
    if target_image_shape is None:
        target_image_shape = (h, w)

    # Pad image to size H, (1+2a)*W
    w_t = tf.cast(
        w, dtype=tf.float32, name=None)
    rnd_w = w_t * n
    paddings = [[0, 0], [rnd_w, rnd_w], [0, 0]]
    padded_img = tf.pad(tf_img, paddings, 'REFLECT')

    # Pad image to size (1+2a)*H, W
    h_t = tf.cast(
        h, dtype=tf.float32, name=None)
    rnd_h = h_t * n
    paddings = [[rnd_h, rnd_h], [0, 0], [0, 0]]
    padded_img = tf.pad(tf_img, paddings, 'REFLECT')

    # Random crop section at original size
    Y_trans = tf.image.random_crop(
        padded_img,
        (target_image_shape + (c,)),
        seed=seed,
        name=None)

    return Y_trans


def random_cutout(tf_img, alpha=0.1, seed=None):
    """
    Cuts random black square out from TF image
    Args:
    image: 3-D tensor with a single image.
    alpha: affects max size of square
    target_image_shape: List/Tuple with target image shape.
    Returns:
    Cutout Image tensor
    """

    # get img shape
    height, width, channel = tf_img.shape

    # get square of random shape less than w*a, h*a
    max_val = tf.cast(tf.minimum(alpha * int(width), alpha * int(height)), dtype = tf.int32)
    size = tf.random_uniform(shape=[], minval=0, maxval=max_val, dtype=tf.int32, seed=seed, name=None)

    # get random xy location of square
    x_loc_upper_bound = width - size
    y_loc_upper_bound = height - size

    x = tf.random_uniform(shape=[], minval=0, maxval=x_loc_upper_bound, dtype=tf.int32, seed=seed, name=None)
    y = tf.random_uniform(shape=[], minval=0, maxval=y_loc_upper_bound, dtype=tf.int32, seed=seed, name=None)

    erase_area = tf.ones([size, size, 3], dtype=tf.float32)
    if erase_area.shape == (0, 0, 3):
        return tf_img
    else:
        mask = 1.0 - tf.image.pad_to_bounding_box(erase_area, y, x, height, width)
        erased_img = tf.multiply(tf_img, mask)
        return erased_img
#----------------------------------------------------------------------------
# Loading data from previous training runs.

def parse_config_for_previous_run(run_dir):
    with open(os.path.join(run_dir, 'submit_config.pkl'), 'rb') as f:
        data = pickle.load(f)
    data = data.get('run_func_kwargs', {})
    return dict(train=data, dataset=data.get('dataset_args', {}))

#----------------------------------------------------------------------------
# Size and contents of the image snapshot grids that are exported
# periodically during training.

def setup_snapshot_image_grid(training_set,
    size    = '1080p',      # '1080p' = to be viewed on 1080p display, '4k' = to be viewed on 4k display.
    layout  = 'random'):    # 'random' = grid contents are selected randomly, 'row_per_class' = each row corresponds to one class label.

    # Select size.
    gw = 1; gh = 1
    if size == '1080p':
        gw = np.clip(1920 // training_set.shape[2], 3, 32)
        gh = np.clip(1080 // training_set.shape[1], 2, 32)
    if size == '4k':
        gw = np.clip(3840 // training_set.shape[2], 7, 32)
        gh = np.clip(2160 // training_set.shape[1], 4, 32)
    if size == '8k':
        gw = np.clip(7680 // training_set.shape[2], 7, 32)
        gh = np.clip(4320 // training_set.shape[1], 4, 32)

    # Initialize data arrays.
    reals = np.zeros([gw * gh] + training_set.shape, dtype=training_set.dtype)
    labels = np.zeros([gw * gh, training_set.label_size], dtype=training_set.label_dtype)

    # Random layout.
    if layout == 'random':
        reals[:], labels[:] = training_set.get_minibatch_np(gw * gh)

    # Class-conditional layouts.
    class_layouts = dict(row_per_class=[gw,1], col_per_class=[1,gh], class4x4=[4,4])
    if layout in class_layouts:
        bw, bh = class_layouts[layout]
        nw = (gw - 1) // bw + 1
        nh = (gh - 1) // bh + 1
        blocks = [[] for _i in range(nw * nh)]
        for _iter in range(1000000):
            real, label = training_set.get_minibatch_np(1)
            idx = np.argmax(label[0])
            while idx < len(blocks) and len(blocks[idx]) >= bw * bh:
                idx += training_set.label_size
            if idx < len(blocks):
                blocks[idx].append((real, label))
                if all(len(block) >= bw * bh for block in blocks):
                    break
        for i, block in enumerate(blocks):
            for j, (real, label) in enumerate(block):
                x = (i %  nw) * bw + j %  bw
                y = (i // nw) * bh + j // bw
                if x < gw and y < gh:
                    reals[x + y * gw] = real[0]
                    labels[x + y * gw] = label[0]

    return (gw, gh), reals, labels

#----------------------------------------------------------------------------
