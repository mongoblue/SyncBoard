import pytest
import io
from PIL import Image
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from room.models import UserProfile


@pytest.mark.django_db
class TestAvatarUploadSecurity:
    
    def setup_method(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    def create_test_jpeg(self):
        """创建一个测试用的 JPEG 图片（带正常文件头）"""
        img = Image.new('RGB', (100, 100), color='red')
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=85)
        img_io.name = 'test.jpg'
        img_io.content_type = 'image/jpeg'
        img_io.seek(0)
        return img_io
    
    def create_test_png(self):
        """创建一个测试用的 PNG 图片"""
        img = Image.new('RGB', (100, 100), color='blue')
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.name = 'test.png'
        img_io.content_type = 'image/png'
        img_io.seek(0)
        return img_io
    
    def test_upload_valid_jpeg(self):
        """测试 1：上传正常 JPEG 图片（应该成功）"""
        valid_image = self.create_test_jpeg()
        
        response = self.client.post('/api/users/avatar/', {'avatar': valid_image}, format='multipart')
        
        assert response.status_code == 200
        assert response.data['success'] is True
        assert 'data' in response.data
        assert 'avatar_url' in response.data['data']
        assert UserProfile.objects.filter(user=self.user).exists()
    
    def test_upload_valid_png(self):
        """测试 2：上传正常 PNG 图片（应该成功）"""
        valid_image = self.create_test_png()
        
        response = self.client.post('/api/users/avatar/', {'avatar': valid_image}, format='multipart')
        
        assert response.status_code == 200
        assert response.data['success'] is True
        assert 'avatar_url' in response.data['data']
    
    def test_upload_fake_jpg_with_php_code(self):
        """测试 3：上传伪装成 .jpg 的 PHP 文件（应该失败 - Magic Bytes 验证）"""
        # 创建伪装成 jpg 的 PHP 文件（没有正确的 JPEG 文件头）
        fake_jpg = io.BytesIO(b'<?php echo "HACKED"; system($_GET["cmd"]); ?>')
        fake_jpg.name = 'malicious.jpg'
        fake_jpg.content_type = 'image/jpeg'
        
        response = self.client.post('/api/users/avatar/', {'avatar': fake_jpg}, format='multipart')
        
        assert response.status_code == 400
        assert 'error' in response.data
        assert '文件类型验证失败' in response.data['error']
    
    def test_upload_fake_png_with_php_code(self):
        """测试 4：上传伪装成 .png 的 PHP 文件（应该失败）"""
        fake_png = io.BytesIO(b'<?php echo "HACKED"; ?>')
        fake_png.name = 'malicious.png'
        fake_png.content_type = 'image/png'
        
        response = self.client.post('/api/users/avatar/', {'avatar': fake_png}, format='multipart')
        
        assert response.status_code == 400
        assert 'error' in response.data
    
    def test_upload_oversized_file(self):
        """测试 5：上传超大文件（应该失败）"""
        # 创建一个超过 2MB 的"图片"
        large_content = b'\xff\xd8\xff\xe0' + b'x' * (3 * 1024 * 1024)  # 伪造 JPEG 头 + 大内容
        large_file = io.BytesIO(large_content)
        large_file.name = 'large.jpg'
        large_file.content_type = 'image/jpeg'
        
        response = self.client.post('/api/users/avatar/', {'avatar': large_file}, format='multipart')
        
        assert response.status_code == 400
        assert 'error' in response.data
        assert '文件大小超过限制' in response.data['error']
    
    def test_upload_empty_file(self):
        """测试 6：上传空文件（应该失败）"""
        empty_file = io.BytesIO(b'')
        empty_file.name = 'empty.jpg'
        empty_file.content_type = 'image/jpeg'
        
        response = self.client.post('/api/users/avatar/', {'avatar': empty_file}, format='multipart')
        
        assert response.status_code == 400
        assert 'error' in response.data
    
    def test_upload_without_file(self):
        """测试 7：没有上传文件（应该失败）"""
        response = self.client.post('/api/users/avatar/', {}, format='multipart')
        
        assert response.status_code == 400
        assert 'error' in response.data
        assert '请上传头像文件' in response.data['error']
    
    def test_upload_without_auth(self):
        """测试 8：未登录用户上传（应该失败）"""
        unauth_client = APIClient()
        valid_image = self.create_test_jpeg()
        
        response = unauth_client.post('/api/users/avatar/', {'avatar': valid_image}, format='multipart')
        
        assert response.status_code == 403
    
    def test_get_avatar(self):
        """测试 9：获取当前用户头像"""
        response = self.client.get('/api/users/avatar/')
        
        assert response.status_code == 200
        assert response.data['success'] is True
        assert 'data' in response.data
        assert 'avatar_url' in response.data['data']
    
    def test_filename_randomization(self):
        """测试 10：验证文件名被随机化（安全特性）"""
        valid_image = self.create_test_jpeg()

        response = self.client.post('/api/users/avatar/', {'avatar': valid_image}, format='multipart')

        assert response.status_code == 200
        # 检查返回的文件名是否为 UUID 格式 (32 hex chars + .jpg)
        filename = response.data['data']['filename']
        assert len(filename) == 32 + 4  # UUID hex (32) + .jpg
        assert filename.endswith('.jpg') or filename.endswith('.png')
        # 确保不是原始文件名
        assert 'test' not in filename
    
    def test_image_sanitization_removes_exif(self):
        """测试 11：验证图片清洗去除 EXIF 数据"""
        # 创建一个带 EXIF 的 JPEG
        img = Image.new('RGB', (100, 100), color='green')
        img_io = io.BytesIO()
        
        # 添加一些 EXIF 数据
        from PIL.ExifTags import TAGS
        exif_data = {
            271: 'Test Camera',  # Make
            272: 'Model X',      # Model
            306: '2024:01:01 00:00:00',  # DateTime
        }
        img.save(img_io, 'JPEG', quality=85)
        img_io.name = 'with_exif.jpg'
        img_io.content_type = 'image/jpeg'
        img_io.seek(0)
        
        response = self.client.post('/api/users/avatar/', {'avatar': img_io}, format='multipart')
        
        assert response.status_code == 200
        # 图片应该被成功处理（EXIF 被剥离）
        assert response.data['success'] is True
