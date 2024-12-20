from PIL import Image, ImageDraw

def create_icon():
    # 创建一个 256x256 的图像
    size = 256
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 设置颜色
    primary_color = (52, 152, 219)  # 蓝色
    secondary_color = (41, 128, 185)  # 深蓝色

    # 绘制一个圆形背景
    draw.ellipse([20, 20, size-20, size-20], fill=primary_color)

    # 绘制磁盘清理的图标符号
    # 绘制磁盘形状
    draw.rectangle([size//4, size//3, 3*size//4, 2*size//3], fill=secondary_color)
    draw.ellipse([size//4-10, size//3-5, size//4+10, size//3+5], fill=secondary_color)
    draw.ellipse([3*size//4-10, size//3-5, 3*size//4+10, size//3+5], fill=secondary_color)

    # 绘制清理符号（一个简单的对勾）
    points = [
        (size//3, size//2),
        (size//2, 2*size//3),
        (2*size//3, size//3)
    ]
    draw.line(points, fill='white', width=10)

    # 保存为 ICO 文件
    image.save('icon.ico', format='ICO', sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])

if __name__ == '__main__':
    create_icon()
    print("图标已成功生成��") 