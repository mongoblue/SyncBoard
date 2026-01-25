from rest_framework import serializers
from .models import Project, Task, Column
from django.contrib.auth.models import User

class UsersSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username'] # 修正：name -> username

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'

class ColumnSerializer(serializers.ModelSerializer):
    # 这一步做的很好！直接嵌套了
    tasks = TaskSerializer(many=True, read_only=True)
    class Meta:
        model = Column
        fields = '__all__'

class ProjectSerializer(serializers.ModelSerializer):
    owner_details = UsersSerializer(source='owner', read_only=True)
    members_details = UsersSerializer(source='members', many=True, read_only=True)
    class Meta:
        model = Project
        fields = '__all__'
