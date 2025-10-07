# terraform/iam.tf
# Least-privilege policy for presigning specific prefix:
# Django will generate presigned URLs for keys under {artifacts_prefix}...
data "aws_iam_policy_document" "signer" {
  statement {
    sid    = "AllowPutGetObjectsInPrefix"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:AbortMultipartUpload"
    ]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/${local.artifacts_prefix}*"
    ]
  }

  # Optional: List for debugging (limits to prefix)
  statement {
    sid    = "AllowListPrefix"
    effect = "Allow"
    actions = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.artifacts_prefix}*"]
    }
  }
}

resource "aws_iam_policy" "signer" {
  name   = "${var.project}-artifacts-signer-${local.env}"
  policy = data.aws_iam_policy_document.signer.json
}

# IAM user for local/CI presigning (toggle with create_signer_user)
resource "aws_iam_user" "signer" {
  count = var.create_signer_user ? 1 : 0
  name  = "${var.project}-signer-${local.env}"
  path  = "/service/"
}

resource "aws_iam_user_policy_attachment" "signer_attach" {
  count      = var.create_signer_user ? 1 : 0
  user       = aws_iam_user.signer[0].name
  policy_arn = aws_iam_policy.signer.arn
}

# Access key for the signer user (for dev only; avoid in prod if using OIDC)
resource "aws_iam_access_key" "signer_key" {
  count = var.create_signer_user && var.create_user_access_key ? 1 : 0
  user  = aws_iam_user.signer[0].name
}
