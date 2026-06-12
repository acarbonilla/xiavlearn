from django.db import models
from django.contrib.auth.models import User


class LearnerProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='learner_profile')
	current_level = models.CharField(max_length=10, blank=True, null=True)
	target_level = models.CharField(max_length=10, default='B2')
	daily_study_minutes = models.PositiveIntegerField(default=30)
	learning_goal = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.user.username


class Skill(models.Model):
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name


class SkillMastery(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skill_masteries')
	skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='masteries')
	level_code = models.CharField(max_length=10, default='A1')
	score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	status = models.CharField(max_length=50, default='Needs Review')
	last_updated = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = (('user', 'skill'),)

	def __str__(self):
		return f"{self.user.username} - {self.skill.name}"


class CurriculumLevel(models.Model):
	level_code = models.CharField(max_length=10, unique=True)
	name = models.CharField(max_length=100)
	description = models.TextField(blank=True)
	sort_order = models.PositiveIntegerField(default=0)

	def __str__(self):
		return self.level_code


class Module(models.Model):
	level = models.ForeignKey(CurriculumLevel, on_delete=models.CASCADE, related_name='modules')
	skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='modules')
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	objectives = models.JSONField(default=list, blank=True)
	sort_order = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)

	def __str__(self):
		return self.title


class StudySession(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_sessions')
	module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name='study_sessions')
	session_type = models.CharField(max_length=50, default='lesson')
	input_text = models.TextField(blank=True)
	ai_feedback = models.TextField(blank=True)
	score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	started_at = models.DateTimeField(auto_now_add=True)
	completed_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return f"{self.user.username} - {self.session_type}"


class StudyPlan(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_plans')
	plan_data = models.JSONField(default=dict, blank=True)
	focus_skills = models.JSONField(default=list, blank=True)
	start_date = models.DateField(null=True, blank=True)
	end_date = models.DateField(null=True, blank=True)
	generated_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.user.username} - {self.generated_at.isoformat()}"
