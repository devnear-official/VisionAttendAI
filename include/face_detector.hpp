#pragma once

#include "dl_detect_base.hpp"
#include "dl_detect_msr_postprocessor.hpp"
#include "dl_detect_mnp_postprocessor.hpp"
#include "dl_image_preprocessor.hpp"
#include "dl_model_base.hpp"
#include "models/msr_model.h"
#include "models/mnp_model.h"

class FaceDetector {
private:
    dl::Model *m_msr_model = nullptr;
    dl::image::ImagePreprocessor *m_msr_preprocessor = nullptr;
    dl::detect::MSRPostprocessor *m_msr_postprocessor = nullptr;

    dl::Model *m_mnp_model = nullptr;
    dl::image::ImagePreprocessor *m_mnp_preprocessor = nullptr;
    dl::detect::MNPPostprocessor *m_mnp_postprocessor = nullptr;

    bool m_initialized = false;

public:
    FaceDetector() {}

    ~FaceDetector() {
        delete m_msr_postprocessor;
        delete m_msr_preprocessor;
        delete m_msr_model;

        delete m_mnp_postprocessor;
        delete m_mnp_preprocessor;
        delete m_mnp_model;
    }

    bool init(float score_thr = 0.5f, float nms_thr = 0.5f) {
        if (m_initialized) return true;

        // Stage 1: MSR
        m_msr_model = new dl::Model(reinterpret_cast<const char *>(msr_model_espdl), fbs::MODEL_LOCATION_IN_FLASH_RODATA);
        if (!m_msr_model) return false;
        m_msr_model->minimize();

        m_msr_preprocessor = new dl::image::ImagePreprocessor(m_msr_model, {0, 0, 0}, {1, 1, 1}, true);
        m_msr_postprocessor = new dl::detect::MSRPostprocessor(
            m_msr_model,
            m_msr_preprocessor,
            score_thr,
            nms_thr,
            10,
            {{8, 8, 9, 9, {{16, 16}, {32, 32}}}, {16, 16, 9, 9, {{64, 64}, {128, 128}}}}
        );

        // Stage 2: MNP
        m_mnp_model = new dl::Model(reinterpret_cast<const char *>(mnp_model_espdl), fbs::MODEL_LOCATION_IN_FLASH_RODATA);
        if (!m_mnp_model) return false;
        m_mnp_model->minimize();

        m_mnp_preprocessor = new dl::image::ImagePreprocessor(m_mnp_model, {0, 0, 0}, {1, 1, 1}, true);
        m_mnp_postprocessor = new dl::detect::MNPPostprocessor(
            m_mnp_model,
            m_mnp_preprocessor,
            score_thr,
            nms_thr,
            10,
            {{1, 1, 0, 0, {{48, 48}}}}
        );

        m_initialized = true;
        return true;
    }

    std::list<dl::detect::result_t> detect(const dl::image::img_t &img) {
        if (!m_initialized) return {};

        // Stage 1: Candidate Proposal
        m_msr_preprocessor->preprocess(img);
        m_msr_model->run();
        m_msr_postprocessor->postprocess();
        m_msr_postprocessor->nms();
        std::list<dl::detect::result_t> &candidates = m_msr_postprocessor->get_result(img.width, img.height);

        if (candidates.empty()) {
            return {};
        }

        // Stage 2: Candidate Refinement
        m_mnp_postprocessor->clear_result();
        for (auto &candidate : candidates) {
            int center_x = (candidate.box[0] + candidate.box[2]) >> 1;
            int center_y = (candidate.box[1] + candidate.box[3]) >> 1;
            int side = std::max(candidate.box[2] - candidate.box[0], candidate.box[3] - candidate.box[1]);
            candidate.box[0] = center_x - (side >> 1);
            candidate.box[1] = center_y - (side >> 1);
            candidate.box[2] = candidate.box[0] + side;
            candidate.box[3] = candidate.box[1] + side;
            candidate.limit_box(img.width, img.height);

            m_mnp_preprocessor->preprocess(img, candidate.box);
            m_mnp_model->run();
            m_mnp_postprocessor->postprocess();
        }
        m_mnp_postprocessor->nms();
        return m_mnp_postprocessor->get_result(img.width, img.height);
    }
};
