import io
import uuid
import struct
import os
import shutil
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import UserProfile

# 配置常量
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png'}

# 文件头签名 (Magic Bytes)
FILE_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',  # JPEG
    b'\x89PNG\r\n\x1a\n': 'image/png',  # PNG
}


def verify_file_signature(file_bytes):
    """
    通过文件头签名验证真实文件类型
    返回: (is_valid, mime_type, error_message)
    """
    if len(file_bytes) < 12:
        return False, None, "文件太小，无法验证"
    
    # 检查 JPEG (多种变体)
    if file_bytes.startswith(b'\xff\xd8\xff'):
        # 进一步检查 JPEG 标记
        if file_bytes[3:4] in [b'\xe0', b'\xe1', b'\xe8', b'\xdb', b'\xee']:
            return True, 'image/jpeg', None
    
    # 检查 PNG
    if file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return True, 'image/png', None
    
    return False, None, "不支持的文件类型或文件已损坏"


def sanitize_image(file_bytes, target_format='PNG'):
    """
    恶意代码清洗核心函数
    1. 使用 Pillow 打开图片
    2. 创建新的 Image 对象，复制内容
    3. 剥离所有 EXIF 元数据
    4. 重新编码保存为纯净格式
    
    返回: (success, sanitized_bytes, error_message)
    """
    try:
        # 在内存中打开图片
        input_buffer = io.BytesIO(file_bytes)
        original_image = Image.open(input_buffer)
        
        # 验证图片格式
        if original_image.format not in ['JPEG', 'PNG']:
            return False, None, f"不支持的图片格式: {original_image.format}"
        
        # 转换为 RGB 模式（去除透明通道，统一处理）
        if original_image.mode in ('RGBA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', original_image.size, (255, 255, 255))
            if original_image.mode == 'P':
                original_image = original_image.convert('RGBA')
            background.paste(original_image, mask=original_image.split()[-1] if original_image.mode == 'RGBA' else None)
            clean_image = background
        elif original_image.mode != 'RGB':
            clean_image = original_image.convert('RGB')
        else:
            clean_image = original_image.copy()
        
        # 保存到内存缓冲区（剥离所有元数据）
        output_buffer = io.BytesIO()
        
        if target_format.upper() == 'JPEG':
            clean_image.save(
                output_buffer,
                format='JPEG',
                quality=85,
                optimize=True,
                progressive=True,
                # 确保不保存任何 EXIF 数据
                exif=b''
            )
            extension = '.jpg'
        else:  # PNG
            clean_image.save(
                output_buffer,
                format='PNG',
                optimize=True,
                # PNG 没有 EXIF，但确保不保存其他元数据
                compress_level=6
            )
            extension = '.png'
        
        output_buffer.seek(0)
        sanitized_bytes = output_buffer.read()
        
        # 清理资源
        original_image.close()
        clean_image.close()
        input_buffer.close()
        output_buffer.close()
        
        return True, sanitized_bytes, extension
        
    except Exception as e:
        return False, None, f"图片处理失败: {str(e)}"


def generate_secure_filename(extension='.png'):
    """
    生成安全的随机文件名
    使用 uuid4 确保唯一性，防止路径遍历攻击
    """
    # 确保扩展名安全
    safe_extension = extension.lower()
    if safe_extension not in {'.jpg', '.jpeg', '.png'}:
        safe_extension = '.png'
    
    # 生成 UUID 文件名
    filename = f"{uuid.uuid4().hex}{safe_extension}"
    return filename


class AvatarUploadView(APIView):
    """
    头像上传视图 - 高安全防护版本
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # 1. 检查是否有文件上传
        if 'avatar' not in request.FILES:
            return Response(
                {"error": "请上传头像文件"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['avatar']
        
        # 2. 文件大小检查
        if uploaded_file.size > MAX_FILE_SIZE:
            return Response(
                {"error": f"文件大小超过限制 (最大 {MAX_FILE_SIZE // 1024 // 1024}MB)"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if uploaded_file.size == 0:
            return Response(
                {"error": "文件不能为空"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. 读取文件内容到内存
        try:
            file_bytes = uploaded_file.read()
        except Exception as e:
            return Response(
                {"error": "读取文件失败"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 4. Magic Bytes 验证（文件头签名验证）
        is_valid, mime_type, error_msg = verify_file_signature(file_bytes)
        if not is_valid:
            return Response(
                {"error": f"文件类型验证失败: {error_msg}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 5. 恶意代码清洗（核心安全步骤）
        target_format = 'JPEG' if mime_type == 'image/jpeg' else 'PNG'
        success, sanitized_bytes, extension = sanitize_image(file_bytes, target_format)
        
        if not success:
            return Response(
                {"error": f"图片处理失败: {extension}"},  # extension 在这里是错误消息
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 6. 生成安全文件名
        secure_filename = generate_secure_filename(extension)
        
        # 7. 保存到模型
        try:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # 强制清理旧头像目录：确保只保留最新的一张
            user_avatar_dir = os.path.join(settings.MEDIA_ROOT, f'avatars/user_{request.user.id}')
            if os.path.exists(user_avatar_dir):
                try:
                    # 直接删除整个目录，save() 时会自动重建
                    shutil.rmtree(user_avatar_dir)
                except Exception as e:
                    print(f"清理旧头像目录失败: {e}")
                    pass
            
            # 保存新头像（使用清洗后的数据）
            # 注意：由于上面删除了目录，这里 save 会自动创建目录并保存文件
            profile.avatar.save(
                secure_filename,
                ContentFile(sanitized_bytes),
                save=True
            )
            
            # 构建完整的 URL
            avatar_url = request.build_absolute_uri(profile.avatar.url)
            
            return Response(
                {
                    "success": True,
                    "message": "头像上传成功",
                    "data": {
                        "avatar_url": avatar_url,
                        "filename": secure_filename,
                        "size": len(sanitized_bytes)
                    }
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {"error": f"保存头像失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get(self, request):
        """获取当前用户头像"""
        try:
            profile = UserProfile.objects.get(user=request.user)
            avatar_url = None
            if profile.avatar:
                avatar_url = request.build_absolute_uri(profile.avatar.url)
            
            return Response({
                "success": True,
                "data": {
                    "avatar_url": avatar_url
                }
            })
        except UserProfile.DoesNotExist:
            return Response({
                "success": True,
                "data": {
                    "avatar_url": None
                }
            })
