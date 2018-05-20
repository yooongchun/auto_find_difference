"""
大家来找茬微信小程序腾讯官方版 自动找出图片差异，并自动点击

"""
__author__ = "yooongchun"
__email__ = "yooongchun@foxmail.com"
__site__ = "www.yooongchun.com"

import cv2
import numpy as np
import os
import time
import sys
import logging
import threading

logging.basicConfig(level=logging.INFO)

DEBUG = False  # 开启debug模式


# 转换图片格式
# adb 工具直接截图保存到电脑的二进制数据流在windows下"\n" 会被解析为"\r\n",
# 这是由于Linux系统下和Windows系统下表示的不同造成的，而Andriod使用的是Linux内核
def convert_img(path):
    with open(path, "br") as f:
        bys = f.read()
        bys_ = bys.replace(b"\r\n", b"\n")  # 二进制流中的"\r\n" 替换为"\n"
    with open(path, "bw") as f:
        f.write(bys_)


# 裁剪图片
def crop_image(im, box=(0.20, 0.93, 0.05, 0.95), gap=38, dis=2):
    '''
    :param path: 图片路径
    :param box: 裁剪的参数：比例
    :param gap: 中间裁除区域
    :param dis: 偏移距离
    :return: 返回裁剪出来的区域
    '''
    h, w = im.shape[0], im.shape[1]
    region = im[int(h * box[2]):int(h * box[3]), int(w * box[0]):int(w * box[1])]
    rh, rw = region.shape[0], region.shape[1]
    region_1 = region[0 + dis: int(rh / 2) - gap + dis, 0: rw]
    region_2 = region[rh - int(rh / 2) + gap: rh, 0:rw]

    return region_1, region_2, region


# 查找不同返回差值图
def diff(img1, img2):
    diff = (img1 - img2)
    # 形态学开运算滤波
    kernel = np.ones((5, 5), np.uint8)
    opening = cv2.morphologyEx(diff, cv2.MORPH_OPEN, kernel)
    return opening


# 去除右上角的多余区域,即显示小程序返回及分享的灰色区域块
def dispose_region(img):
    h, w = img.shape[0], img.shape[1]
    img[0:int(0.056 * h), int(0.68 * w):w] = 0
    return img


# 查找轮廓中心返回坐标值
def contour_pos(img, num=5, filter_size=5):
    '''
    :param img: 查找的目标图,需为二值图
    :param num: 返回的轮廓数量，如果该值大于轮廓总数，则返回轮廓总数
    :return: 返回值为轮廓的最小外接圆的圆心坐标和半径，存放在一个list中
    '''

    position = []  # 保存返回值
    # 计算轮廓
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    kernel = np.ones((filter_size, filter_size), np.uint8)
    opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)  # 开运算
    image, contours, hierarchy = cv2.findContours(np.max(opening) - opening, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # 根据轮廓周长大小决定返回的轮廓
    arclen = [cv2.arcLength(contour, True) for contour in contours]
    arc = arclen.copy()
    arc.sort(reverse=True)
    if len(arc) >= num:
        thresh = arc[num - 1]
    else:
        thresh = arc[len(arc) - 1]
    for index, contour in enumerate(contours):
        if cv2.arcLength(contour, True) < thresh:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        center = (int(x), int(y))
        radius = int(radius)
        position.append({"center": center, "radius": radius})
    return position


# 在原图上显示
def dip_diff(origin, region, region_1, region_2, dispose_img, position, box, setting_radius=40, gap=38, dis=2):
    for pos in position:
        center, radius = pos["center"], pos["radius"]
        if setting_radius is not None:
            radius = setting_radius
        cv2.circle(region_2, center, radius, (0, 0, 255), 5)
    h, w = region_1.shape[0], region_1.shape[1]
    region[0:h, 0:w] *=dispose_img 
    region[h + gap * 2 - dis:2 * h + gap * 2 - dis, 0:w] = region_2
    orih, oriw = origin.shape[0], origin.shape[1]
    origin[int(orih * box[2]):int(orih * box[3]), int(oriw * box[0]):int(oriw * box[1])] = region
    cv2.namedWindow("show diff", cv2.WINDOW_NORMAL)
    cv2.imshow("show diff", origin)
    cv2.waitKey(0)


# 在原图上绘制圆
def draw_circle(origin, region_1, position, box, gap=38, dis=2):
    h, w = origin.shape[0], origin.shape[1]
    rh = region_1.shape[0]
    for pos in position:
        center, radius = pos["center"], pos["radius"]
        radius = 40
        x = int(w * box[0] + center[0])
        y = int(h * box[2] + rh - dis + 2 * gap + center[1])
        cv2.circle(origin, (x, y), radius, (0, 0, 255), 3)
    cv2.namedWindow("origin with diff", cv2.WINDOW_NORMAL)
    cv2.imshow("origin with diff", origin)
    cv2.waitKey(0)


# 自动点击
def auto_click(origin, region_1, box, position, gap=38, dis=2):
    h, w = origin.shape[0], origin.shape[1]
    rh = region_1.shape[0]
    for pos in position:
        center, radius = pos["center"], pos["radius"]
        x = int(w * box[0] + center[0])
        y = int(h * box[2] + rh - dis + 2 * gap + center[1])
        os.system("adb.exe shell input tap %d %d" % (x, y))
        logging.info("tap:(%d,%d)" % (x, y))
        time.sleep(0.05)


# 主函数入口
def main(argv):
    # 参数列表，程序运行需要提供的参数
    # box = None  # 裁剪原始图像的参数，分别为宽和高的比例倍
    # gap = None  # 图像中间间隔的一半大小
    # dis = None  # 图像移位，微调系数
    # num = None  # 显示差异的数量
    # filter_sz = None  # 滤波核大小
    # auto_clicked=True
    # 仅有一个参数，则使用默认参数
    if len(argv) == 1:
        box = (0.20, 0.93, 0.05, 0.95)
        gap = 38
        dis = 2
        num = 5
        filter_sz = 13
        auto_clicked = "True"
    else:  # 多个参数时需要进行参数解析,参数使用等号分割
        try:
            # 设置参数
            para_pairs = {}
            paras = argv[1:]  # 参数
            for para in paras:
                para_pairs[para.split("=")[0]] = para.split("=")[1]
            # 参数配对
            if "gap" in para_pairs.keys():
                gap = int(para_pairs["gap"])
            else:
                gap = 38
            if "box" in para_pairs.keys():
                box = tuple([float(i) for i in para_pairs["box"][1:-1].split(",")])
            else:
                box = (0.20, 0.93, 0.05, 0.95)
            if "dis" in para_pairs.keys():
                dis = int(para_pairs["dis"])
            else:
                dis = 2
            if "num" in para_pairs.keys():
                num = int(para_pairs["num"])
            else:
                num = 5
            if "filter_sz" in para_pairs.keys():
                filter_sz = int(para_pairs["filter_sz"])
            else:
                filter_sz = 13
            if "auto_clicked" in para_pairs.keys():
                auto_clicked = para_pairs["auto_clicked"]
            else:
                auto_clicked = "True"
        except IOError:
            logging.info("参数出错，请重新输入！")
            return
    st = time.time()
    try:
        os.system("adb.exe exec-out screencap -p >screenshot.png")
        convert_img("screenshot.png")
    except IOError:
        logging.info("从手机获取图片出错，请检查adb工具是否安装及手机是否正常连接！")
        return
    logging.info(">>>从手机截图用时：%0.2f 秒\n" % (time.time() - st))
    st = time.time()
    try:
        origin = cv2.imread("screenshot.png")  # 原始图像
        region_1, region_2, region = crop_image(origin, box=box, gap=gap, dis=dis)
        diff_img = diff(region_1, region_2)
        dis_img = dispose_region(diff_img)
        position = contour_pos(dis_img, num=num, filter_size=filter_sz)
        while len(position) < num and filter_sz > 3:
            filter_sz -= 1
            position = contour_pos(dis_img, num=num, filter_size=filter_sz)
    except IOError:
        logging.info("处理图片出错！")
        return
    try:
        if auto_clicked == "True":
            threading.Thread(target=auto_click, args=(origin, region_1, box, position, gap, dis)).start()
    except IOError:
        logging.info(">>>尝试点击出错！")
    logging.info(">>>处理图片用时：%0.2f 秒\n" % (time.time() - st))
    try:
        dip_diff(origin, region, region_1, region_2, dis_img, position, box)
        # draw_circle(origin, region_1, position, box, gap=gap, dis=dis)
    except IOError:
        logging.info("重组显示出错！")
        return


if __name__ == "__main__":
    if not DEBUG:
        while True:
            main(sys.argv)
    else:
        box = (0.19, 0.95, 0.05, 0.95)
        gap = 38
        dis = 2
        num = 5
        filter_sz = 13
        origin = cv2.imread("c:/users/fanyu/desktop/adb/screenshot.png")  # 原始图像
        region_1, region_2, region = crop_image(origin, box=box, gap=gap, dis=dis)
        cv2.namedWindow("", cv2.WINDOW_NORMAL)
        cv2.imshow("", region_2)
        diff_img = diff(region_1, region_2)
        dis_img = dispose_region(diff_img)
        position = contour_pos(dis_img, num=num, filter_size=filter_sz)
        dip_diff(origin, region, region_1, region_2, dis_img, position, box)
        # draw_circle(origin, region_1, position, box, gap=gap, dis=dis)
