library(lme4)

# 小湖北 (xiaohubei) 示例数据：面积(area)、无性系(Clone)、编号/数量(Numb)
xiaohubei <- data.frame(
  Clone = factor(rep(c("C1", "C2", "C3"), each = 6)),
  Numb = rep(1:6, times = 3),
  area = c(12.1, 14.2, 15.0, 16.2, 17.1, 18.0,
           11.5, 13.0, 14.1, 15.2, 16.0, 17.2,
           13.0, 14.5, 15.8, 16.5, 17.8, 18.5)
)

mod_W_1 <- lmer(area ~ (1|Clone) + Numb, data = xiaohubei)
summary(mod_W_1)

vc <- VarCorr(mod_W_1)
print("vc", vc)
sigma_g <- vc$Clone[[1]]  # Clone的方差
sigma_e <- attr(vc, "sc")^2       # 残差方差

# 计算遗传力
H2 <- sigma_g / (sigma_g + sigma_e)

print("sigma_g", sigma_g)
print("sigma_e", sigma_e)
print("H2", H2)

BLUP <- ranef(mod_W_1)
blup_clone <- BLUP$Clone

blup_clone$Trait <- "Area"
names(blup_clone) <- c("BLUP", "Area")

head(blup_clone)