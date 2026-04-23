"""
视频转码脚本 - 将视频转换为浏览器兼容的 H.264/AAC 格式
使用 imageio-ffmpeg 提供的 ffmpeg
"""
import os
import sys
import shutil

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

import imageio_ffmpeg

from course.models import UploadVideo

def get_ffmpeg_path():
    """获取 ffmpeg 路径"""
    return imageio_ffmpeg.get_ffmpeg_exe()

def transcode_video(input_path, output_path):
    """使用 ffmpeg 转码视频为 H.264/AAC 格式"""
    ffmpeg_path = get_ffmpeg_path()
    
    cmd = [
        ffmpeg_path, '-y', '-i', input_path,
        '-c:v', 'libx264',          # H.264 视频编码
        '-preset', 'medium',         # 编码速度
        '-crf', '23',               # 质量 (0-51, 越小越好)
        '-c:a', 'aac',              # AAC 音频编码
        '-b:a', '128k',             # 音频比特率
        '-movflags', '+faststart',   # 优化 web 播放
        output_path
    ]
    
    print(f"    执行命令: {' '.join(cmd[:5])}...")
    
    try:
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"    错误输出: {result.stderr[:500]}")
        return result.returncode == 0
    except Exception as e:
        print(f"    转码失败: {e}")
        return False

def main():
    # 检查 ffmpeg
    videos = UploadVideo.objects.all()
    total = videos.count()
    converted = 0
    failed = 0
    
    print(f"Starting transcoding {total} video(s)...")
    
    for video in videos:
        if not video.video:
            continue
            
        input_path = video.video.path
        
        # 强制重新转码所有非标准格式视频
        if not input_path.endswith('.mp4'):
            print(f"Skipping (not MP4): {video.title}")
            continue
        
        # 检查是否是 H.264 编码
        import subprocess
        ffmpeg_path = get_ffmpeg_path()
        check_cmd = [ffmpeg_path, '-i', input_path]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        is_h264 = 'Video: h264' in result.stderr or 'Video: avc' in result.stderr
        
        if is_h264:
            print(f"Skipping (already H.264): {video.title}")
            continue
        
        # 生成临时转码文件
        temp_output = input_path.rsplit('.', 1)[0] + '.mp4'
        
        print(f"Transcoding: {video.title}...")
        
        if transcode_video(input_path, temp_output):
            # 删除原文件
            try:
                os.remove(input_path)
            except:
                pass
            
            # 重命名转码后的文件
            os.rename(temp_output, input_path)
            
            converted += 1
            print(f"  [OK] Done: {video.title}")
        else:
            failed += 1
            print(f"  [FAIL] Failed: {video.title}")
    
    print(f"\nTranscoding complete: Success {converted}, Failed {failed}")

if __name__ == '__main__':
    main()
