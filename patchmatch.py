import random
import numpy as np
import cv2
from tqdm import tqdm
import numba
import multiprocessing
from joblib import Parallel, delayed

def getNormalizedFx(Fx,y,x):
    vector = Fx[0][y][x]
    return vector/norms(vector)

def makeFinImage(img,Phi,patch):
    temp = np.zeros_like(img[0])
    height = len(img[0])
    width = len(img[0][0])
    for y in range(height):
        for x in range(width):
            positions = getPatchPosition(img[0], y, x, patch,height,width)
            count=0
            sumX =0
            sumY=0
            R=0
            G=0
            B=0
            for pos in positions:
                if pos[0] != -1 or pos[1]!=-1:
                    count+=1
                    R += img[0][int(Phi[pos[0]][pos[1]][0])][int(Phi[pos[0]][pos[1]][1])][0]
                    G += img[0][int(Phi[pos[0]][pos[1]][0])][int(Phi[pos[0]][pos[1]][1])][1]
                    B += img[0][int(Phi[pos[0]][pos[1]][0])][int(Phi[pos[0]][pos[1]][1])][2]


            temp[y][x][0] = int(R/float(count))
            temp[y][x][1] = int(G/float(count))
            temp[y][x][2] = int(B/float(count))

    return temp

def getPatchPosition(image, imY, imX, patch,height,width):
    points=[]
    len_mx1 = -int(patch[0]/2)
    len_px1 = int(patch[0]/2)+1
    len_mx2 = -int(patch[1]/2)
    len_px2 = int(patch[1]/2)+1
    for x in range(len_mx1,len_px1):
        tempX = imX+x
        for y in range(len_mx2,len_px2):
            if 0 <= tempX < width and 0<= imY+y < height:
                points.append([imY+y,tempX])
            else:
                points.append([-1,-1])
    return points

@numba.jit
def warp(image,Phi,patch):
    ret = np.zeros_like(image)
    height = len(Phi)
    width = len(Phi[0])
    for y in range(height):
        for x in range(width):
            newY = int(Phi[y][x][0])
            newX = int(Phi[y][x][1])
            ret[0][y][x] += image[0][newY][newX]
    return ret

@numba.jit
def norms(vector):
    return np.sqrt(np.dot(vector,vector))

#patchmatchで用いるエネルギー関数を出力する
def getDistance(A,ANormlizeMap,AdashNormlizedMap,By,Bx,BNormlizedMap,BdashNormlizedMap,patch,height,width):
    B = getPatchPosition(BNormlizedMap,By,Bx,patch,height,width)
    sumationA = 0
    sumationB = 0
    length = len(A)
    count=0
    for i in range(length):
        addressAY = A[i][0]
        addressAX = A[i][1]
        addressBY = B[i][0]
        addressBX = B[i][1]
        tempA=0
        tempB=0

        if addressAX!=-1 and addressBX!=-1:
            tempA = (ANormlizeMap[addressAY][addressAX] -BNormlizedMap[addressBY][addressBX])
                                   
            tempB =  (AdashNormlizedMap[addressAY][addressAX] -BdashNormlizedMap[addressBY][addressBX])
            count+=1

        sumationA += np.dot(tempA,tempA)
        sumationB += np.dot(tempB,tempB)
    return (sumationA+sumationB)/float(count)

@numba.jit
def getNormlizedMap(imgA, imgAdash, imgB, imgBdash):
    ANormlizeMap=imgA[0]/np.linalg.norm(imgA[0],ord=2,axis=(2),keepdims=True)
    AdashNormlizedMap=imgAdash[0]/np.linalg.norm(imgAdash[0],ord=2,axis=(2),keepdims=True)
    BNormlizedMap=imgB[0]/np.linalg.norm(imgB[0],ord=2,axis=(2),keepdims=True)
    BdashNormlizedMap=imgBdash[0]/np.linalg.norm(imgBdash[0],ord=2,axis=(2),keepdims=True)
    return ANormlizeMap, AdashNormlizedMap, BNormlizedMap, BdashNormlizedMap


#指定された位置の半径(randomwalkarea)分の有効な座標を返す
def getSearchPosition(image, imY, imX, randomWalkArea,height,width):
    len_mx1 = -int(randomWalkArea[0]/2)
    len_px1 = int(randomWalkArea[0]/2)+1
    len_mx2 = -int(randomWalkArea[1]/2)
    len_px2 = int(randomWalkArea[1]/2)+1
    
    serchX =  np.random.randint(max(imX+len_mx1, 0),min(imX+len_px1,height))
    serchY =  np.random.randint(max(imY+len_mx2, 0),min(imY+len_px2,width ))
    return [int(serchY),int(serchX)]


def randomSearch(A, ANormlizeMap, AdashNormlizedMap, imY, imX, BNormlizedMap, BdashNormlizedMap, randomWalkArea, patch, height, width):
    minimum = getDistance(A, ANormlizeMap, AdashNormlizedMap, imY, imX, BNormlizedMap, BdashNormlizedMap, patch, height, width)

    saveY=imY
    saveX=imX
    maxHeight= randomWalkArea[0]
    maxWidth = randomWalkArea[1]

    while maxHeight > 1:
        points=getSearchPosition(BNormlizedMap, imY, imX, [maxHeight, maxWidth], height, width)

        tempY = points[0]
        tempX = points[1]

        dis = getDistance(A, ANormlizeMap, AdashNormlizedMap, tempY, tempX, BNormlizedMap, BdashNormlizedMap, patch, height, width)

        if minimum > dis:
            minimum = dis
            saveY = tempY
            saveX = tempX
        maxHeight //=2
        maxWidth  //=2
    return [saveY,saveX]

# @numba.jit
def patchMatchA(imgA, imgAdash, imgB, imgBdash, randomWalkArea, patch, Phi,i):
    height=len(imgA[0])
    width =len(imgA[0][0])
    ANormlizeMap, AdashNormlizedMap, BNormlizedMap, BdashNormlizedMap = getNormlizedMap(imgA, imgAdash, imgB, imgBdash)
    
    ret = np.zeros_like(Phi)
    
    for y in tqdm(range(height)):
        for x in range(width):
            positionList=[Phi[y][x]]
            minimum = 100000
            arcs=[1]
            # arcs=[16,8,4,2,1]
            for arc in arcs:
                if y-arc>=0:#up
                    positionList.append(Phi[y-arc][x])
                if x-arc>=0:#left
                    positionList.append(Phi[y][x-arc])
                if y+arc<height:#down
                    positionList.append(Phi[y+arc][x])
                if x+arc<width:#right
                    positionList.append(Phi[y][x+arc])

            saveX=x
            saveY=y
            
            tempY=0
            tempX=0
            A = getPatchPosition(ANormlizeMap,y, x, patch,height,width)

            #一番値が近いエリアを探索
            for i,pos in enumerate(positionList):
                tempY = int(pos[0])
                tempX = int(pos[1])

                dis = getDistance(A, ANormlizeMap,AdashNormlizedMap, tempY, tempX, BNormlizedMap,BdashNormlizedMap, patch, height,width)
                if minimum > dis:
                    minimum = dis
                    saveY = tempY
                    saveX = tempX

            #一番値が近いエリアのみを保存
            minimum = 100000000

            ret[y][x]=randomSearch(A, ANormlizeMap, AdashNormlizedMap, saveY,saveX, BNormlizedMap, BdashNormlizedMap, randomWalkArea, patch, height, width)
    return ret

@numba.jit
def Phi2Image(Phi):
    ret = np.zeros((len(Phi),len(Phi[0]),3))
    for y in range(len(Phi)):
        for x in range(len(Phi[y])):
            ret[y][x] = [Phi[y][x][1],0,Phi[y][x][0]]
    ret = 255*ret/np.max(ret)
    ret = np.clip(ret,0,255)
    ret = np.asarray(ret,dtype='uint8')
    return ret
